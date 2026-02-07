Based on the provided minified source code, here are the GraphQL queries, mutations, and fragments found within.

### Fragments

**Job Opening Info Fragment**

```graphql
fragment JobPubOpeningInfoFragment on Job {
  ciphertext
  id
  type
  access
  title
  hideBudget
  createdOn
  notSureProjectDuration
  notSureFreelancersToHire
  notSureExperienceLevel
  notSureLocationPreference
  premium
}
```

**Job Segmentation Data Fragment**

```graphql
fragment JobPubOpeningSegmentationDataFragment on JobSegmentation {
  customValue
  label
  name
  sortOrder
  type
  value
  skill {
    description
    externalLink
    prettyName
    skill
    id
  }
}
```

**Job Sand Data Fragment**

```graphql
fragment JobPubOpeningSandDataFragment on SandsData {
  occupation {
    freeText
    ontologyId
    prefLabel
    id
    uid: id
  }
  ontologySkills {
    groupId
    id
    freeText
    prefLabel
    groupPrefLabel
    relevance
  }
  additionalSkills {
    groupId
    id
    freeText
    prefLabel
    relevance
  }
}
```

**Job Public Opening Fragment**
_(Note: Interpolates previous fragments)_

```graphql
fragment JobPubOpeningFragment on JobPubOpeningInfo {
  status
  postedOn
  publishTime
  sourcingTime
  startDate
  deliveryDate
  workload
  contractorTier
  description
  info {
    ...JobPubOpeningInfoFragment
  }
  segmentationData {
    ...JobPubOpeningSegmentationDataFragment
  }
  sandsData {
    ...JobPubOpeningSandDataFragment
  }
  category {
    name
    urlSlug
  }
  categoryGroup {
    name
    urlSlug
  }
  budget {
    amount
    currencyCode
  }
  annotations {
    customFields
    tags
  }
  engagementDuration {
    label
    weeks
  }
  extendedBudgetInfo {
    hourlyBudgetMin
    hourlyBudgetMax
    hourlyBudgetType
  }
  attachments @include(if: $isLoggedIn) {
    fileName
    length
    uri
  }
  clientActivity {
    lastBuyerActivity
    totalApplicants
    totalHired
    totalInvitedToInterview
    unansweredInvites
    invitationsSent
    numberOfPositionsToHire
  }
  deliverables
  deadline
  tools {
    name
  }
}
```

**Job Qualifications Fragment**

```graphql
fragment JobQualificationsFragment on JobQualifications {
  countries
  earnings
  groupRecno
  languages
  localDescription
  localFlexibilityDescription
  localMarket
  minJobSuccessScore
  minOdeskHours
  onSiteType
  prefEnglishSkill
  regions
  risingTalent
  shouldHavePortfolio
  states
  tests
  timezones
  type
  locationCheckRequired
  group {
    groupId
    groupLogo
    groupName
  }
  location {
    city
    country
    countryTimezone
    offsetFromUtcMillis
    state
    worldRegion
  }
  locations {
    id
    type
  }
  minHoursWeek @skip(if: $isLoggedIn)
}
```

**Job Auth Details Opening Fragment**
_(Interpolates previous fragments)_

```graphql
fragment JobAuthDetailsOpeningFragment on JobAuthOpeningInfo {
  job {
    ...JobPubOpeningFragment
  }
  qualifications {
    ...JobQualificationsFragment
  }
  questions {
    question
    position
  }
}
```

**Job Buyer Info Fragment**

```graphql
fragment JobPubBuyerInfoFragment on JobPubBuyerInfo {
  location {
    offsetFromUtcMillis
    countryTimezone
    city
    country
  }
  stats {
    totalAssignments
    activeAssignmentsCount
    hoursCount
    feedbackCount
    score
    totalJobsWithHires
    totalCharges {
      amount
    }
  }
  company {
    name @include(if: $isLoggedIn)
    companyId @include(if: $isLoggedIn)
    isEDCReplicated
    contractDate
    profile {
      industry
      size
    }
  }
  jobs {
    openCount
    postedCount @include(if: $isLoggedIn)
    openJobs {
      id
      uid: id
      isPtcPrivate
      ciphertext
      title
      type
    }
  }
  avgHourlyJobsRate @include(if: $isLoggedIn) {
    amount
  }
}
```

**Buyer Work History Fragment**

```graphql
fragment JobAuthDetailsBuyerWorkHistoryFragment on BuyerWorkHistoryItem {
  isPtcJob
  status
  isEDCReplicated
  isPtcPrivate
  startDate
  endDate
  totalCharge
  totalHours
  jobInfo {
    title
    id
    uid: id
    access
    type
    ciphertext
  }
  contractorInfo {
    contractorName
    accessType
    ciphertext
  }
  rate {
    amount
  }
  feedback {
    feedbackSuppressed
    score
    comment
  }
  feedbackToClient {
    feedbackSuppressed
    score
    comment
  }
}
```

**Job Auth Details Buyer Fragment**
_(Interpolates previous fragments)_

```graphql
fragment JobAuthDetailsBuyerFragment on JobAuthBuyerInfo {
  enterprise
  isPaymentMethodVerified
  info {
    ...JobPubBuyerInfoFragment
  }
  workHistory {
    ...JobAuthDetailsBuyerWorkHistoryFragment
  }
}
```

**Current User Info Fragment**

```graphql
fragment JobAuthDetailsCurrentUserInfoFragment on JobCurrentUserInfo {
  owner
  freelancerInfo {
    profileState
    applied
    devProfileCiphertext
    hired
    application {
      vjApplicationId
    }
    pendingInvite {
      inviteId
    }
    contract {
      contractId
      status
    }
    hourlyRate {
      amount
    }
    qualificationsMatches {
      matches {
        clientPreferred
        clientPreferredLabel
        freelancerValue
        freelancerValueLabel
        qualification
        qualified
      }
    }
  }
}
```

**Similar Jobs Fragment**

```graphql
fragment JobPubSimilarJobsFragment on PubSimilarJob {
  id
  ciphertext
  title
  description
  engagement
  durationLabel
  contractorTier
  type
  createdOn
  renewedOn
  amount {
    amount
  }
  maxAmount {
    amount
  }
  ontologySkills {
    id
    prefLabel
  }
  hourlyBudgetMin
  hourlyBudgetMax
}
```

### Queries

**Job Auth Details Query**
_(Interpolates fragments)_

```graphql
query JobAuthDetailsQuery($id: ID!, $isFreelancerOrAgency: Boolean!, $isLoggedIn: Boolean!) {
  jobAuthDetails(id: $id) {
    hiredApplicantNames
    opening {
      ...JobAuthDetailsOpeningFragment
    }
    buyer {
      ...JobAuthDetailsBuyerFragment
    }
    currentUserInfo {
      ...JobAuthDetailsCurrentUserInfoFragment
    }
    similarJobs {
      id
      uid: id
      ciphertext
      title
      snippet
    }
    workLocation {
      onSiteCity
      onSiteCountry
      onSiteReason
      onSiteReasonFlexible
      onSiteState
      onSiteType
    }
    phoneVerificationStatus {
      status
    }
    applicantsBidsStats {
      avgRateBid {
        amount
        currencyCode
      }
      minRateBid {
        amount
        currencyCode
      }
      maxRateBid {
        amount
        currencyCode
      }
    }
    specializedProfileOccupationId @include(if: $isFreelancerOrAgency)
    applicationContext @include(if: $isFreelancerOrAgency) {
      freelancerAllowed
      clientAllowed
    }
  }
}
```

**Job Public Details Query**
_(Interpolates fragments)_

```graphql
query JobPubDetailsQuery($id: ID!, $isLoggedIn: Boolean!) {
  jobPubDetails(id: $id) {
    opening {
      ...JobPubOpeningFragment
    }
    qualifications {
      ...JobQualificationsFragment
    }
    buyer {
      ...JobPubBuyerInfoFragment
    }
    similarJobs {
      ...JobPubSimilarJobsFragment
    }
    buyerExtra {
      isPaymentMethodVerified
    }
  }
}
```

**Similar Jobs Query**
_(Interpolates fragments)_

```graphql
query SimilarJobsQuery($ciphertext: String!) {
  similarJobs(ciphertext: $ciphertext) {
    ...JobPubSimilarJobsFragment
  }
}
```

**Get Enterprise Job Info**

```graphql
query getEnterpriseJobInfoQuery($jobId: ID!) {
  organization {
    isPurchaseOrderEnabled: featureInCurrentSubscription(feature: MNY_FEATURE_PURCHASE_ORDERS) {
      featureInCurrentSubscription
    }
    isCustomFieldsEnabled: featureInCurrentSubscription(feature: MNY_FEATURE_CUSTOM_FIELDS) {
      featureInCurrentSubscription
    }
    isEnterpriseIndicationEnabled: featureInCurrentSubscription(
      feature: MNY_FEATURE_ENTERPRISE_INDICATION
    ) {
      featureInCurrentSubscription
    }
  }
  purchaseOrderInfo: enterpriseJobPurchaseOrderInfo(jobId: $jobId) {
    orderNumber
    placeholder
    description
  }
  customFieldsInfo: enterpriseJobCustomFieldsInfo(jobId: $jobId) {
    customFieldsConfig {
      fieldId
      rawType
      type
      label
      dropdownItems {
        id
        fieldId
        displayValue
        value
        active
        description
      }
    }
    customFieldValues {
      fieldId
      value
      readOnlyDisplayValue
    }
    onBehalfOfPersonName
  }
}
```

**Get First Redirect**

```graphql
query getFirstRedirect(
  $forceDisableCache: Boolean
  $orgId: ID
  $userId: ID
  $redirectType: String
) {
  firstRedirect(
    personId: $userId
    forceDisableCache: $forceDisableCache
    orgId: $orgId
    redirectType: $redirectType
  ) {
    description
    redirectId
    redirectUrl
  }
}
```

**Organization Context**

```graphql
query {
  organization {
    id
    type
    legacyType
    flag {
      client
      vendor
      agency
      individual
    }
  }
  companySelector {
    items {
      organizationId
      organizationRid
      organizationEnterpriseType
      organizationType
      organizationLegacyType
      typeTitle
      title
      photoUrl
      monetizedTitle
    }
    profilePortrait {
      portrait100
    }
  }
}
```

**User Context**

```graphql
query {
  user {
    id
    rid
    nid
  }
  requestMetadata {
    sudo
  }
}
```

**VPN Context**

```graphql
query {
  requestMetadata {
    internal
  }
}
```

**Get Job Slug By Occupation**

```graphql
query ($occupationUid: ID!, $jobType: MetadataType!) {
  visitor {
    siteMetadataSearchRecords(
      type: $jobType
      filter: { occupationUids_any: [$occupationUid], main_eq: true, indexable_eq: true }
      pagination: { first: 1, after: "0" }
    ) {
      id
      type
      name
      slug
      modifier
    }
  }
}
```

**Job Applications (Agency Owner)**
_(Note: JS variable interpolation present)_

```graphql
query {
  jobApplicationsAgency(jobId: "${t.jobId}") {
    applications {
      applicationId
      userId
    }
  }

  staffList: getStaffListByTeamId(teamId: "${t.orgId}", limit: 100, hierarchy: true) {
    totalCount
    staffs {
      userId: id
      firstName
      lastName
    }
  }
}
```

**Job Applications (Agency Sub-Team)**
_(Note: JS variable interpolation present)_

```graphql
query {
  jobApplicationsAgency(jobId: "${o}", teamId: "${s}") {
    applications {
      applicationId
      userId
    }
  }

  staffList: getStaffListByTeamId(teamId: "${s}", limit: 100) {
    totalCount
    staffs {
      userId: id
      firstName
      lastName
    }
  }
}
```

**Agency Teams For Proposals**

```graphql
query {
  agencyTeamsForProposals: subTeamsForProposals {
    teamId
    access
  }
}
```

**Is Agency Owner Check**
_(Note: JS variable interpolation present)_

```graphql
query {
  staffsByPersonId(
    personId: "${n}"
    staffType: "Ownership"
    orgLegacyType: Vendor
    orgType: Business
  ) {
    edges {
      node {
        owner
        orgId
      }
    }
  }
}
```

**Freelancer Applications**

```graphql
query ($jobId: ID!) {
  jobApplications: jobApplicationsFreelancer(jobId: $jobId) {
    applications {
      id
      firstName
      lastName
    }
    canSubmitMoreProposals
  }
}
```

**Can Apply On Behalf Of Agency**

```graphql
query canApplyOnBehalfOfAgency($agencyId: ID!) {
  canApplyOnBehalfOfAgencyFreelancers(agencyId: $agencyId)
}
```

**Check User Permissions**

```graphql
query checkUserPermissions($resourceType: ResourceType!, $action: String!) {
  user {
    permissions(
      filter: {
        resourceType_eq: $resourceType
        actions_any: [$action]
        performExternalChecks_eq: true
        returnAllTeams: true
      }
    ) {
      edges {
        node {
          access
        }
      }
    }
  }
}
```

**Connects Data (Freelancer)**

```graphql
query connectsDataForFreelancer($jobId: ID!) {
  pricingJobPost: jobConnectsPriceFreelancer(jobId: $jobId) {
    price
    context
    auctionPrice
  }
  connectsSummary: jobFreelancerConnectsSummary {
    connectsBalance
  }
  jobFeatureInCurrentSubscription(feature: VIEW_COMPETITOR_BIDS) {
    featureInCurrentSubscription
  }
  chooseConnectsModalStatus {
    isExplainerModalShown
  }
}
```

**Connects Data (Agency)**

```graphql
query connectsDataForAgency($jobId: ID!, $freelancerId: ID!, $agencyId: ID) {
  pricingJobPost: pricingJobPostByFreelancer(
    jobPostId: $jobId
    freelancerPersonId: $freelancerId
    agencyOrgId: $agencyId
  ) {
    price
    context
    auctionPrice
  }
  connectsSummary {
    connectsBalance
  }
  organization {
    featureInCurrentSubscription(feature: VIEW_COMPETITOR_BIDS) {
      featureInCurrentSubscription
    }
  }
  chooseConnectsModalStatus {
    isExplainerModalShown
  }
}
```

**AI Interview Status**

```graphql
query ($jobPostingId: ID!) {
  aiInterviewer {
    jobStatus(jobPostingId: $jobPostingId) {
      jobPostingId
      aiInterviewerEnabled
    }
  }
}
```

**Get AI Interview Status For User**

```graphql
query GetAiInterviewStatusForUser($jobPostingId: ID!) {
  aiInterviewer {
    interviewStatus(jobPostingId: $jobPostingId) {
      interviewStatus
      joinLimitReached
    }
  }
}
```

**Check Flags (New Freelancer Bonus)**

```graphql
query ($userId: ID!) {
  hasFlag(flag: NEW_FL_BONUS, userId: $userId) {
    value
  }
  rulesBatchEvaluateGeneric(
    expressionList: {
      expressions: ["RegisteredAfter(2024-08-12) and not ExclusiveAgencyContractor"]
    }
  ) {
    evaluations {
      result
    }
  }
}
```

**Get User Preferences**
_(Note: JS variable interpolation present)_

```graphql
{
  componentUserPreferences(
    input: {globalOrganization: ${e},component: "${t}", prefKey: "${n}" }
  ) {
    componentName
    preferences {
      key
      value
    }
  }
}
```

### Mutations

**User Intent Evaluation**

```graphql
mutation userIntentEvaluation($jobId: ID) {
  stepUpVerificationEvaluation(
    flowType: "viewJobDetails"
    jobId: $jobId
    intents: [DEFAULT]
    checkpoint: SUBMIT_PROPOSAL
  ) {
    decision
    additionalDetails
  }
}
```

**Create User Preferences**
_(Note: JS variable interpolation present)_

```graphql
mutation {
  createComponentUserPreferences(
    input: {
      component: "${t}"
      globalOrganization: ${e}
      preferences: [${n.map(o=>`{ key: "${o.key}", value: "${o.value}" }`)}]
    }
  )
}
```

**Create Incognia Transaction**
_(Note: JS variable interpolation present)_

```graphql
mutation {
  createInTransaction(incogniaTransactionRequest: { incogniaToken: "${t}", checkpoint: ${e}, originDevice: WEB })
}
```

**Update Choose Connects Modal Status**

```graphql
mutation {
  updateChooseConnectsModalStatus(status: true) {
    isExplainerModalShown
  }
}
```

**Start Interview**

```graphql
mutation StartInterview($jobPostingId: ID!, $input: AiInterviewerStartInterviewInput!) {
  aiInterviewer {
    startInterview(jobPostingId: $jobPostingId, input: $input) {
      roomId
      interviewStatus
    }
  }
}
```

**Send Interview Link**

```graphql
mutation SendInterviewLink($jobPostingId: ID!) {
  aiInterviewer {
    sendInterviewLink(jobPostingId: $jobPostingId)
  }
}
```

### Dynamic/Template Queries

_These use dynamic generation logic in the source code:_

**Quantitative Test Allocation**

```javascript
// Constructed via loop in function e8
query {
  user { ... }
  organization { ... }
  visitor { ... }
}
```

**Allocate Quantitative Test Auto**

```javascript
// Constructed via loop in function t8
mutation {
  allocateUserToQuantitativeTestAuto(...) { ... }
  allocateOrganizationToQuantitativeTestAuto(...) { ... }
  allocateVisitorToQuantitativeTestAuto(...) { ... }
}
```

**Feature Flags**

```javascript
// Constructed in function s8
query {
  featureFlag(name: "...", visitorId: "...") { value }
}
```

## Upworker Notes (2026-02-07)

- Upwork job search GraphQL no longer exposes `connectPrice` on `AuthJobSearchResult` (the field triggers `FieldUndefined`).
- To keep connects pricing/balance, use a separate query:
  - `connectsDataForFreelancer` via `jobConnectsPriceFreelancer(jobId: ...)` (see the Connects Data section above).
- If you see `Requested oAuth2 client does not have permission ...`, the token/headers you're using are not the same as the Upwork web app.
  - Capture the browser request `Authorization` and any required extra headers/cookies and reuse them in the worker.
