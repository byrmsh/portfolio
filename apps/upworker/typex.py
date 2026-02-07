from typing import List, Literal, Optional, TypedDict, Union

import pydantic


class UpworkOntologySkill(TypedDict):
    uid: str
    parentSkillUid: Optional[str]
    prefLabel: str
    prettyName: str
    freeText: Optional[str]
    highlighted: bool


class UpworkFixedPriceAmount(TypedDict):
    isoCurrencyCode: Optional[str]
    amount: str


class UpworkClientInfo(TypedDict):
    paymentVerificationStatus: Optional[str]
    country: Optional[str]
    totalReviews: int
    totalFeedback: float
    hasFinancialPrivacy: bool
    totalSpent: Optional[UpworkFixedPriceAmount]


class UpworkFreelancerClientRelation(TypedDict):
    lastContractRid: Optional[str]
    companyName: Optional[str]
    lastContractTitle: Optional[str]


class UpworkHistoryData(TypedDict):
    client: UpworkClientInfo
    freelancerClientRelation: UpworkFreelancerClientRelation


class UpworkFixedPriceEngagementDuration(TypedDict):
    rid: int
    label: str
    weeks: int
    ctime: str
    mtime: str


class UpworkJobDetails(TypedDict):
    id: str
    ciphertext: str
    jobType: Literal["FIXED", "HOURLY"]
    weeklyRetainerBudget: Optional[float]
    hourlyBudgetMax: Optional[float]
    hourlyBudgetMin: Optional[float]
    hourlyEngagementType: Optional[str]
    contractorTier: str
    sourcingTimestamp: Optional[str]
    createTime: str
    publishTime: str
    enterpriseJob: bool
    personsToHire: int
    premium: bool
    totalApplicants: Optional[int]
    hourlyEngagementDuration: Optional[UpworkFixedPriceEngagementDuration]
    fixedPriceAmount: Optional[UpworkFixedPriceAmount]
    fixedPriceEngagementDuration: Optional[UpworkFixedPriceEngagementDuration]


class UpworkJobTile(TypedDict):
    job: UpworkJobDetails


class UpworkFacetValue(TypedDict):
    key: str
    value: int


class UpworkFacets(TypedDict):
    jobType: List[UpworkFacetValue]
    workload: List[UpworkFacetValue]
    clientHires: List[UpworkFacetValue]
    durationV3: List[UpworkFacetValue]
    amount: List[UpworkFacetValue]
    contractorTier: List[UpworkFacetValue]
    contractToHire: List[UpworkFacetValue]
    paymentVerified: List[UpworkFacetValue]
    proposals: List[UpworkFacetValue]
    previousClients: List[UpworkFacetValue]


class UpworkPaging(TypedDict):
    total: int
    offset: int
    count: int


class UpworkJobResult(TypedDict):
    id: str
    title: str
    description: str
    relevanceEncoded: str
    ontologySkills: List[UpworkOntologySkill]
    isSTSVectorSearchResult: bool
    applied: Optional[bool]
    upworkHistoryData: UpworkHistoryData
    jobTile: UpworkJobTile


class UpworkUserJobSearchV1(TypedDict):
    paging: UpworkPaging
    facets: UpworkFacets
    results: List[UpworkJobResult]


class UpworkUniversalSearchNuxt(TypedDict):
    userJobSearchV1: UpworkUserJobSearchV1


class UpworkJobSearch(TypedDict):
    universalSearchNuxt: UpworkUniversalSearchNuxt


class UpworkJobSearchData(TypedDict):
    search: UpworkJobSearch


class UpworkJobSearchResponse(TypedDict):
    data: UpworkJobSearchData


class EmbeddedClientConf(TypedDict):
    id: str
    token: str


ClientConfValidator = pydantic.TypeAdapter(EmbeddedClientConf)
HeadersValidator = pydantic.TypeAdapter(dict[str, str])


class InitialLoginTop(TypedDict):
    message: str
    type: str


class InitialLoginPayloadLogin(TypedDict):
    mode: str
    username: str
    rememberme: bool
    elapsedTime: int
    forterToken: str
    deviceType: str
    password: str


class InitialLoginPayload(TypedDict):
    login: InitialLoginPayloadLogin


InitialLoginPayloadValidator = pydantic.TypeAdapter(InitialLoginPayload)


class SuccessfulLoginResponse(TypedDict):
    success: Literal[1]
    redirectUrl: str
    userNid: str


class SuspiciousLoginAlertTop(TypedDict):
    message: str
    type: str


class SuspiciousLoginAlerts(TypedDict):
    top: List[SuspiciousLoginAlertTop]


class SuspiciousLoginResponse(TypedDict):
    success: Literal[0]
    alerts: SuspiciousLoginAlerts
    eventCode: str
    authToken: str
    requestId: None
    securityCheckCertificate: str


LoginResponse = Union[SuccessfulLoginResponse, SuspiciousLoginResponse]
