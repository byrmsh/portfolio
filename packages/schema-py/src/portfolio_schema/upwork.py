from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

# Mirrors the current Upwork payload shape defined by apps/upworker/typex.py
# and selected in apps/upworker/job-search.gql.

class UpworkBaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpworkOntologySkill(UpworkBaseSchema):
    uid: str
    parentSkillUid: str | None
    prefLabel: str
    prettyName: str
    freeText: str | None
    highlighted: bool


class UpworkFixedPriceAmount(UpworkBaseSchema):
    isoCurrencyCode: str | None
    amount: str


class UpworkClientInfo(UpworkBaseSchema):
    paymentVerificationStatus: str | None
    country: str | None
    totalReviews: int
    totalFeedback: float
    hasFinancialPrivacy: bool
    totalSpent: UpworkFixedPriceAmount | None


class UpworkFreelancerClientRelation(UpworkBaseSchema):
    lastContractRid: str | None
    companyName: str | None
    lastContractTitle: str | None


class UpworkHistoryData(UpworkBaseSchema):
    client: UpworkClientInfo
    freelancerClientRelation: UpworkFreelancerClientRelation


class UpworkEngagementDuration(UpworkBaseSchema):
    rid: int
    label: str
    weeks: int
    ctime: str
    mtime: str


class UpworkJobDetails(UpworkBaseSchema):
    id: str
    ciphertext: str
    jobType: Literal["FIXED", "HOURLY"]
    weeklyRetainerBudget: float | None
    hourlyBudgetMax: float | None
    hourlyBudgetMin: float | None
    hourlyEngagementType: str | None
    contractorTier: str
    sourcingTimestamp: str | None
    createTime: str
    publishTime: str
    enterpriseJob: bool
    personsToHire: int
    premium: bool
    totalApplicants: int | None
    hourlyEngagementDuration: UpworkEngagementDuration | None
    fixedPriceAmount: UpworkFixedPriceAmount | None
    fixedPriceEngagementDuration: UpworkEngagementDuration | None


class UpworkJobTile(UpworkBaseSchema):
    job: UpworkJobDetails


class UpworkFacetValue(UpworkBaseSchema):
    key: str
    value: int


class UpworkFacets(UpworkBaseSchema):
    jobType: list[UpworkFacetValue]
    workload: list[UpworkFacetValue]
    clientHires: list[UpworkFacetValue]
    durationV3: list[UpworkFacetValue]
    amount: list[UpworkFacetValue]
    contractorTier: list[UpworkFacetValue]
    contractToHire: list[UpworkFacetValue]
    paymentVerified: list[UpworkFacetValue]
    proposals: list[UpworkFacetValue]
    previousClients: list[UpworkFacetValue]


class UpworkPaging(UpworkBaseSchema):
    total: int
    offset: int
    count: int


class UpworkJobResult(UpworkBaseSchema):
    id: str
    title: str
    description: str
    relevanceEncoded: str
    ontologySkills: list[UpworkOntologySkill]
    isSTSVectorSearchResult: bool
    connectPrice: int | None
    applied: bool | None
    upworkHistoryData: UpworkHistoryData
    jobTile: UpworkJobTile


class UpworkUserJobSearchV1(UpworkBaseSchema):
    paging: UpworkPaging
    facets: UpworkFacets
    results: list[UpworkJobResult]


class UpworkUniversalSearchNuxt(UpworkBaseSchema):
    userJobSearchV1: UpworkUserJobSearchV1


class UpworkJobSearch(UpworkBaseSchema):
    universalSearchNuxt: UpworkUniversalSearchNuxt


class UpworkJobSearchData(UpworkBaseSchema):
    search: UpworkJobSearch


class UpworkJobSearchResponse(UpworkBaseSchema):
    data: UpworkJobSearchData


UpworkJobResultValidator = TypeAdapter(UpworkJobResult)
UpworkJobSearchResponseValidator = TypeAdapter(UpworkJobSearchResponse)


def validate_upwork_job_result(payload: object) -> UpworkJobResult:
    return UpworkJobResultValidator.validate_python(payload)


def validate_upwork_job_search_response(payload: object) -> UpworkJobSearchResponse:
    return UpworkJobSearchResponseValidator.validate_python(payload)
