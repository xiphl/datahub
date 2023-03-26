import logging
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Union

from pydantic import validator
from pydantic.fields import Field

import datahub.metadata.schema_classes as models
from datahub.configuration.common import ConfigModel
from datahub.configuration.config_loader import load_config_file
from datahub.emitter.mce_builder import datahub_guid, make_group_urn, make_user_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.api.decorators import (  # SourceCapability,; capability,
    SupportStatus,
    config_class,
    platform_name,
    support_status,
)
from datahub.ingestion.api.source import Source, SourceReport
from datahub.ingestion.api.workunit import MetadataWorkUnit, UsageStatsWorkUnit
from datahub.ingestion.graph.client import DataHubGraph
from datahub.utilities.registries.domain_registry import DomainRegistry
from datahub.utilities.urn_encoder import UrnEncoder

logger = logging.getLogger(__name__)

valid_status: models.StatusClass = models.StatusClass(removed=False)

# This needed to map path presents in inherits, contains, values, and related_terms to terms' optional id
path_vs_id: Dict[str, Optional[str]] = {}


class Owners(ConfigModel):
    users: Optional[List[str]]
    groups: Optional[List[str]]


class KnowledgeCard(ConfigModel):
    url: Optional[str]
    label: Optional[str]


class GlossaryTermConfig(ConfigModel):
    id: Optional[str]
    name: str
    description: str
    term_source: Optional[str]
    source_ref: Optional[str]
    source_url: Optional[str]
    owners: Optional[Owners]
    inherits: Optional[List[str]]
    contains: Optional[List[str]]
    values: Optional[List[str]]
    related_terms: Optional[List[str]]
    custom_properties: Optional[Dict[str, str]]
    knowledge_links: Optional[List[KnowledgeCard]]
    domain: Optional[str]


class GlossaryNodeConfig(ConfigModel):
    id: Optional[str]
    name: str
    description: str
    owners: Optional[Owners]
    terms: Optional[List[GlossaryTermConfig]]
    nodes: Optional[List["GlossaryNodeConfig"]]
    knowledge_links: Optional[List[KnowledgeCard]]


GlossaryNodeConfig.update_forward_refs()


class DefaultConfig(ConfigModel):
    """Holds defaults for populating fields in glossary terms"""

    source: str
    owners: Owners
    url: Optional[str] = None
    source_type: Optional[str] = "INTERNAL"


class BusinessGlossarySourceConfig(ConfigModel):
    file: Union[str, pathlib.Path] = Field(
        description="Path to business glossary file to ingest. This can be in the form of a URL or local file YAML."
    )
    enable_auto_id: bool = Field(
        description="Generate id field from GlossaryNode and GlossaryTerm's name field",
        default=False,
    )


class BusinessGlossaryConfig(DefaultConfig):
    version: str
    nodes: Optional[List[GlossaryNodeConfig]]
    terms: Optional[List[GlossaryTermConfig]]

    @validator("version")
    def version_must_be_1(cls, v):
        if v != "1":
            raise ValueError("Only version 1 is supported")
        return v


def create_id(path: List[str], default_id: Optional[str], enable_auto_id: bool) -> str:
    if default_id is not None:
        return default_id  # No need to create id from path as default_id is provided

    id_: str = ".".join(path)

    if UrnEncoder.contains_reserved_char(id_):
        enable_auto_id = True

    if enable_auto_id:
        id_ = datahub_guid({"path": id_})
    return id_


def make_glossary_node_urn(
    path: List[str], default_id: Optional[str], enable_auto_id: bool
) -> str:
    if default_id is not None and default_id.startswith("urn:li:glossaryNode:"):
        logger.debug(
            f"node's default_id({default_id}) is in urn format for path {path}. Returning same as urn"
        )
        return default_id

    return "urn:li:glossaryNode:" + create_id(path, default_id, enable_auto_id)


def make_glossary_term_urn(
    path: List[str], default_id: Optional[str], enable_auto_id: bool
) -> str:
    if default_id is not None and default_id.startswith("urn:li:glossaryTerm:"):
        logger.debug(
            f"term's default_id({default_id}) is in urn format for path {path}. Returning same as urn"
        )
        return default_id

    return "urn:li:glossaryTerm:" + create_id(path, default_id, enable_auto_id)


def get_owners(owners: Owners) -> models.OwnershipClass:
    owners_meta: List[models.OwnerClass] = []
    if owners.users is not None:
        owners_meta = owners_meta + [
            models.OwnerClass(
                owner=make_user_urn(o),
                type=models.OwnershipTypeClass.DEVELOPER,
            )
            for o in owners.users
        ]
    if owners.groups is not None:
        owners_meta = owners_meta + [
            models.OwnerClass(
                owner=make_group_urn(o),
                type=models.OwnershipTypeClass.DEVELOPER,
            )
            for o in owners.groups
        ]
    return models.OwnershipClass(owners=owners_meta)


def get_mces(
    glossary: BusinessGlossaryConfig,
    ingestion_config: BusinessGlossarySourceConfig,
    ctx: PipelineContext,
) -> Iterable[Union[MetadataChangeProposalWrapper, models.MetadataChangeEventClass]]:
    path: List[str] = []
    root_owners = get_owners(glossary.owners)

    if glossary.nodes:
        for node in glossary.nodes:
            yield from get_mces_from_node(
                node,
                path + [node.name],
                parentNode=None,
                parentOwners=root_owners,
                defaults=glossary,
                ingestion_config=ingestion_config,
                ctx=ctx,
            )

    if glossary.terms:
        for term in glossary.terms:
            yield from get_mces_from_term(
                term,
                path + [term.name],
                parentNode=None,
                parentOwnership=root_owners,
                defaults=glossary,
                ingestion_config=ingestion_config,
                ctx=ctx,
            )


def get_mce_from_snapshot(snapshot: Any) -> models.MetadataChangeEventClass:
    return models.MetadataChangeEventClass(proposedSnapshot=snapshot)


def make_institutional_memory_mcp(
    urn: str, knowledge_cards: List[KnowledgeCard]
) -> Optional[MetadataChangeProposalWrapper]:
    elements: List[models.InstitutionalMemoryMetadataClass] = []

    for knowledge_card in knowledge_cards:
        if knowledge_card.label and knowledge_card.url:
            elements.append(
                models.InstitutionalMemoryMetadataClass(
                    url=knowledge_card.url,
                    description=knowledge_card.label,
                    createStamp=models.AuditStampClass(
                        time=int(time.time() * 1000.0),
                        actor="urn:li:corpuser:datahub",
                        message="ingestion bot",
                    ),
                )
            )

    if elements:
        return MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=models.InstitutionalMemoryClass(elements=elements),
        )

    return None


def make_domain_mcp(
    term_urn: str, domain_aspect: models.DomainsClass
) -> MetadataChangeProposalWrapper:
    return MetadataChangeProposalWrapper(entityUrn=term_urn, aspect=domain_aspect)


def get_mces_from_node(
    glossaryNode: GlossaryNodeConfig,
    path: List[str],
    parentNode: Optional[str],
    parentOwners: models.OwnershipClass,
    defaults: DefaultConfig,
    ingestion_config: BusinessGlossarySourceConfig,
    ctx: PipelineContext,
) -> Iterable[Union[MetadataChangeProposalWrapper, models.MetadataChangeEventClass]]:
    node_urn = make_glossary_node_urn(
        path, glossaryNode.id, ingestion_config.enable_auto_id
    )
    node_info = models.GlossaryNodeInfoClass(
        definition=glossaryNode.description,
        parentNode=parentNode,
        name=glossaryNode.name,
    )
    node_owners = parentOwners
    if glossaryNode.owners is not None:
        assert glossaryNode.owners is not None
        node_owners = get_owners(glossaryNode.owners)

    node_snapshot = models.GlossaryNodeSnapshotClass(
        urn=node_urn,
        aspects=[node_info, node_owners, valid_status],
    )
    yield get_mce_from_snapshot(node_snapshot)

    if glossaryNode.knowledge_links is not None:
        mcp: Optional[MetadataChangeProposalWrapper] = make_institutional_memory_mcp(
            node_urn, glossaryNode.knowledge_links
        )
        if mcp is not None:
            yield mcp

    if glossaryNode.nodes:
        for node in glossaryNode.nodes:
            yield from get_mces_from_node(
                node,
                path + [node.name],
                parentNode=node_urn,
                parentOwners=node_owners,
                defaults=defaults,
                ingestion_config=ingestion_config,
                ctx=ctx,
            )

    if glossaryNode.terms:
        for term in glossaryNode.terms:
            yield from get_mces_from_term(
                glossaryTerm=term,
                path=path + [term.name],
                parentNode=node_urn,
                parentOwnership=node_owners,
                defaults=defaults,
                ingestion_config=ingestion_config,
                ctx=ctx,
            )


def get_domain_class(
    graph: Optional[DataHubGraph], domains: List[str]
) -> models.DomainsClass:
    # FIXME: In the ideal case, the domain registry would be an instance variable so that it
    # preserves its cache across calls to this function. However, the current implementation
    # requires the full list of domains to be passed in at instantiation time, so we can't
    # actually do that.
    domain_registry: DomainRegistry = DomainRegistry(
        cached_domains=[k for k in domains], graph=graph
    )
    domain_class = models.DomainsClass(
        domains=[domain_registry.get_domain_urn(domain) for domain in domains]
    )
    return domain_class


def get_mces_from_term(
    glossaryTerm: GlossaryTermConfig,
    path: List[str],
    parentNode: Optional[str],
    parentOwnership: models.OwnershipClass,
    defaults: DefaultConfig,
    ingestion_config: BusinessGlossarySourceConfig,
    ctx: PipelineContext,
) -> Iterable[Union[models.MetadataChangeEventClass, MetadataChangeProposalWrapper]]:
    term_urn = make_glossary_term_urn(
        path, glossaryTerm.id, ingestion_config.enable_auto_id
    )
    aspects: List[
        Union[
            models.GlossaryTermInfoClass,
            models.GlossaryRelatedTermsClass,
            models.OwnershipClass,
            models.StatusClass,
            models.GlossaryTermKeyClass,
            models.BrowsePathsClass,
        ]
    ] = []
    term_info = models.GlossaryTermInfoClass(
        definition=glossaryTerm.description,
        termSource=glossaryTerm.term_source  # type: ignore
        if glossaryTerm.term_source is not None
        else defaults.source_type,
        sourceRef=glossaryTerm.source_ref
        if glossaryTerm.source_ref
        else defaults.source,
        sourceUrl=glossaryTerm.source_url if glossaryTerm.source_url else defaults.url,
        parentNode=parentNode,
        customProperties=glossaryTerm.custom_properties,
        name=glossaryTerm.name,
    )
    aspects.append(term_info)

    is_a = None
    has_a = None
    values: Union[None, List[str]] = None
    related_terms: Union[None, List[str]] = None
    if glossaryTerm.inherits is not None:
        assert glossaryTerm.inherits is not None
        is_a = [
            make_glossary_term_urn(
                [term],
                default_id=path_vs_id.get(term),
                enable_auto_id=ingestion_config.enable_auto_id,
            )
            for term in glossaryTerm.inherits
        ]
    if glossaryTerm.contains is not None:
        assert glossaryTerm.contains is not None
        has_a = [
            make_glossary_term_urn(
                [term],
                default_id=path_vs_id.get(term),
                enable_auto_id=ingestion_config.enable_auto_id,
            )
            for term in glossaryTerm.contains
        ]
    if glossaryTerm.values is not None:
        assert glossaryTerm.values is not None
        values = [
            make_glossary_term_urn(
                [term],
                default_id=path_vs_id.get(term),
                enable_auto_id=ingestion_config.enable_auto_id,
            )
            for term in glossaryTerm.values
        ]
    if glossaryTerm.related_terms is not None:
        assert glossaryTerm.related_terms is not None
        related_terms = [
            make_glossary_term_urn(
                [term],
                default_id=path_vs_id.get(term),
                enable_auto_id=ingestion_config.enable_auto_id,
            )
            for term in glossaryTerm.related_terms
        ]

    if (
        is_a is not None
        or has_a is not None
        or values is not None
        or related_terms is not None
    ):
        related_term_aspect = models.GlossaryRelatedTermsClass(
            isRelatedTerms=is_a,
            hasRelatedTerms=has_a,
            values=values,
            relatedTerms=related_terms,
        )
        aspects.append(related_term_aspect)

    ownership: models.OwnershipClass = parentOwnership
    if glossaryTerm.owners is not None:
        assert glossaryTerm.owners is not None
        ownership = get_owners(glossaryTerm.owners)
    aspects.append(ownership)

    if glossaryTerm.domain is not None:
        yield make_domain_mcp(
            term_urn, get_domain_class(ctx.graph, [glossaryTerm.domain])
        )

    term_snapshot: models.GlossaryTermSnapshotClass = models.GlossaryTermSnapshotClass(
        urn=term_urn,
        aspects=aspects,
    )
    yield get_mce_from_snapshot(term_snapshot)

    if glossaryTerm.knowledge_links:
        mcp: Optional[MetadataChangeProposalWrapper] = make_institutional_memory_mcp(
            term_urn, glossaryTerm.knowledge_links
        )
        if mcp is not None:
            yield mcp


def populate_path_vs_id(glossary: BusinessGlossaryConfig) -> None:
    path: List[str] = []

    def _process_child_terms(parent_node: GlossaryNodeConfig, path: List[str]) -> None:
        path_vs_id[".".join(path + [parent_node.name])] = parent_node.id

        if parent_node.terms:
            for term in parent_node.terms:
                path_vs_id[".".join(path + [parent_node.name] + [term.name])] = term.id

        if parent_node.nodes:
            for node in parent_node.nodes:
                _process_child_terms(node, path + [parent_node.name])

    if glossary.nodes:
        for node in glossary.nodes:
            _process_child_terms(node, path)

    if glossary.terms:
        for term in glossary.terms:
            path_vs_id[".".join(path + [term.name])] = term.id


@platform_name("Business Glossary")
@config_class(BusinessGlossarySourceConfig)
@support_status(SupportStatus.CERTIFIED)
@dataclass
class BusinessGlossaryFileSource(Source):
    """
    This plugin pulls business glossary metadata from a yaml-formatted file. An example of one such file is located in the examples directory [here](https://github.com/datahub-project/datahub/blob/master/metadata-ingestion/examples/bootstrap_data/business_glossary.yml).
    """

    config: BusinessGlossarySourceConfig
    report: SourceReport = field(default_factory=SourceReport)

    @classmethod
    def create(cls, config_dict, ctx):
        config = BusinessGlossarySourceConfig.parse_obj(config_dict)
        return cls(ctx, config)

    def load_glossary_config(
        self, file_name: Union[str, pathlib.Path]
    ) -> BusinessGlossaryConfig:
        config = load_config_file(file_name)
        glossary_cfg = BusinessGlossaryConfig.parse_obj(config)
        return glossary_cfg

    def get_workunits(self) -> Iterable[Union[MetadataWorkUnit, UsageStatsWorkUnit]]:
        glossary_config = self.load_glossary_config(self.config.file)
        populate_path_vs_id(glossary_config)
        for event in get_mces(
            glossary_config, ingestion_config=self.config, ctx=self.ctx
        ):
            if isinstance(event, models.MetadataChangeEventClass):
                wu = MetadataWorkUnit(f"{event.proposedSnapshot.urn}", mce=event)
                self.report.report_workunit(wu)
                yield wu
            elif isinstance(event, MetadataChangeProposalWrapper):
                wu = MetadataWorkUnit(
                    id=f"{event.entityType}-{event.aspectName}-{event.entityUrn}",
                    mcp=event,
                )
                yield wu

    def get_report(self):
        return self.report
