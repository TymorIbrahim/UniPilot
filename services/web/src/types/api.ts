export type User = {
  id: string
  email: string
  status: string
}

export type AuthPayload = {
  accessToken: string
  user: User
}

export type StudentProfile = {
  id: string
  userId: string
  institutionId: string
  facultyId?: string | null
  programType: string
  degreeId: string | null
  catalogYear: number
  currentSemesterCode: string
  academicPath?: StudentAcademicPath
  preferences?: {
    maxCreditsPerSemester?: number
  }
}

export type AcademicPathSelection = {
  kind: 'bsc_track' | 'minor' | 'special_program' | 'graduate_program' | 'dne_specialization'
  trackSlug?: string | null
  programCode?: string | null
  label?: string | null
}

export type StudentAcademicPath = {
  trackSlug?: string | null
  minors?: AcademicPathSelection[]
  specialPrograms?: AcademicPathSelection[]
  graduatePrograms?: AcademicPathSelection[]
  specializations?: AcademicPathSelection[]
}

export type CourseSummary = {
  id?: string
  courseNumber: string
  title?: string
  titleHebrew?: string
  faculty?: string
  credits?: number
  semesterOfferingSummary?: {
    academicYear: number
    semesterCode: number
    slotTypes?: string[]
    instructors?: string
  }
}

export type PaginatedCourses = {
  items: CourseSummary[]
  total: number
  limit: number
  offset: number
}

export type DegreeProgram = {
  id?: string
  programCode: string
  name?: string
  nameHebrew?: string
  nameEn?: string
  totalCredits?: number
  metadata?: {
    wikiPage?: string
    faculty?: string
    facultyId?: string
    programKind?: string
  }
}

export type CatalogFaculty = {
  id?: string
  facultyId: string
  institutionId: string
  wikiSlug: string
  name?: string
  nameHe?: string
  nameEn?: string
  aliases?: string[]
  catalogPrefix?: string
}

export type CatalogPathOption = {
  id?: string
  optionKey: string
  facultyId: string
  wikiSlug: string
  kind:
    | 'bsc_track'
    | 'special_program'
    | 'minor'
    | 'graduate_program'
    | 'dne_specialization'
    | string
  name?: string
  nameHe?: string
  nameEn?: string
  studyLevels?: string[]
  selectableAsPrimary?: boolean
  linkedProgramCode?: string
  linkedDegreeProgramId?: string
  description?: string
  duration?: string
  totalCreditsRequired?: string
}

export type ParsedTranscriptCourse = {
  courseNumber: string
  semesterCode: string
  grade: number
  creditsEarned: number
  attempt?: number | null
  title?: string | null
  confidence: number
  warnings: string[]
}

export type TranscriptParsePreview = {
  courses: ParsedTranscriptCourse[]
  studentId?: string | null
  studentName?: string | null
  warnings: string[]
  parseMetadata: {
    pageCount: number
    extractor: string
    pipelineVersion: string
    textCharCount: number
    ocrUsed: boolean
    transcriptFormat?: string
    showsAllAttempts?: boolean
  }
}

export type TranscriptImportResult = {
  created: CompletedCourse[]
  skippedDuplicates: string[]
  unresolved: Array<{ courseNumber: string; semesterCode: string; reason: string }>
  createdCount: number
  skippedCount: number
  unresolvedCount: number
  replacedCount?: number
}

export type CompletedCourse = {
  id: string
  courseId: string
  courseNumber?: string
  courseTitle?: string
  semesterCode: string
  grade: string
  gradePoints?: number | null
  creditsEarned: number
  attempt: number
  source: string
  recordedAt?: string
  metadata?: {
    passGrade?: boolean
    exemption?: boolean
    importSource?: string
    importedTitle?: string
  }
}

export type CourseProgressEntry = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  catalogCredits?: number
  creditsEarned?: number
  grade?: string | number
  semesterCode?: string
  assignedPoolGroupId?: string | null
}

export type PoolConstraintEvaluation = {
  requirementGroupId?: string
  title?: string
  operator?: string
  status?: string
  stepsCompleted?: number
  stepsRequired?: number
  creditsCompleted?: number
  creditsRequired?: number
  satisfied?: boolean
  usedPhysics1mRule?: boolean
}

export type PoolConstraintsSummary = {
  constraintsSatisfied?: boolean
  mandatoryPools?: PoolConstraintEvaluation[]
  focusChains?: PoolConstraintEvaluation[]
  scienceSupplement?: PoolConstraintEvaluation | null
  allPools?: PoolConstraintEvaluation[]
}

export type ProgressAdvisoryWarning = {
  code: string
  severity?: string
  message: string
  courseNumber?: string
  completedSemesterIndex?: number
}

export type RequirementProgressEntry = {
  requirementId?: string
  requirementGroupId: string
  title?: string
  requirementType?: string
  isMandatory?: boolean
  requirementEnforcement?: string
  eligibilityEnforcement?: 'strict_pool' | 'credit_bucket_only' | string
  linkedPoolGroupId?: string | null
  status: string
  minCredits: number
  creditsCompleted: number
  creditsRemaining: number
  completedCourses?: CourseProgressEntry[]
  remainingCourses?: CourseProgressEntry[]
  poolConstraints?: PoolConstraintsSummary | null
}

export type MissingRequirementEntry = {
  requirementId?: string
  requirementGroupId: string
  title?: string
  requirementType?: string
  isMandatory?: boolean
  status: string
  creditsCompleted: number
  creditsRequired: number
  creditsRemaining: number
  remainingCourseCount?: number
  eligibilityEnforcement?: string
}

export type IneligibleCreditEntry = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  creditsEarned: number
  reason?: string
  linkedPoolGroupId?: string
  bucketSuffix?: string
}

export type GraduationProgress = {
  degreeId: string
  degreeCode?: string
  degreeName?: string
  catalogYear?: number
  catalogVersion?: string
  completedCredits: number
  transcriptCreditsTotal?: number
  degreeAppliedCredits?: number
  totalRequiredCredits: number
  creditsRemaining: number
  completionPercentage: number
  completedMandatoryCourses?: CourseProgressEntry[]
  remainingMandatoryCourses?: CourseProgressEntry[]
  completedElectiveCredits?: number
  remainingElectiveCredits?: number
  requirementProgress?: RequirementProgressEntry[]
  missingRequirements?: MissingRequirementEntry[]
  ineligibleCredits?: IneligibleCreditEntry[]
  assumptions?: string[]
  assumptionKeys?: string[]
  catalogOverlapEquivalenceGroups?: string[][]
  advisoryWarnings?: ProgressAdvisoryWarning[]
  statusSummary: string
}

export type CurriculumCreditsDisplay = {
  display: string
  value: number | null
  uncertain: boolean
  range?: { min: number; max: number } | null
}

export type CurriculumDataQuality = {
  manualReviewRequired: boolean
  confidence: string
  hasAlternatives: boolean
  creditsUncertain: boolean
  verifyWithRegistrar: boolean
  sourceNotes?: string[]
}

export type CurriculumGraphNode = {
  nodeId: string
  courseNumber: string
  title?: string
  semester: number
  credits: CurriculumCreditsDisplay
  alternatives: string[]
  dataQuality: CurriculumDataQuality
  prerequisiteNumbers: string[]
  status:
    | 'completed'
    | 'failed'
    | 'in_progress'
    | 'available'
    | 'blocked'
    | 'verify_with_registrar'
  missingPrerequisites: string[]
  isBottleneck: boolean
  satisfiedViaAlternative?: string
}

export type CurriculumGraphEdge = {
  from: string
  to: string
  kind: 'prerequisite' | 'corequisite' | 'external_prerequisite'
  requirementType?: 'hard' | 'catalog_text' | 'external' | 'corequisite'
  highlight?: string
}

export type ElectiveBucketRule = {
  type: string
  operator?: string | null
  chooseCount?: number | null
  chain?: string | null
  minCredits?: number | null
  allowedPrefixes?: string[]
}

export type ElectivePoolCourse = {
  courseNumber: string
  title?: string
  titleHe?: string
  credits?: number | null
  alternatives?: string[]
  notes?: string[]
}

export type PoolProgressDisplay =
  | 'chain_steps'
  | 'dedicated_bucket_credits'
  | 'shared_bucket_credits'
  | 'none'

export type ElectiveBucket = {
  groupId: string
  title?: string
  requirementType?: string
  minCredits?: number | null
  linkedCreditBucketId?: string | null
  rule: ElectiveBucketRule
  allowedPrefixes?: string[]
  courses: ElectivePoolCourse[]
  courseCount: number
  courseListSource?: 'explicit' | 'prefix_catalog' | 'vault_union' | 'empty'
  progressDisplay?: PoolProgressDisplay
  coursesTruncated?: boolean
  advisoryOnly?: boolean
  manualReviewRequired?: boolean
  notes?: string[]
  catalogDescription?: string | null
  explorerReady?: boolean
}

export type CurriculumGraph = {
  trackSlug: string
  programCode: string
  catalogYear: number
  catalogVersion: string
  viewDefault: 'semester_swimlanes' | 'mind_map'
  semesterLanes: Array<{
    semester: number
    title: string
    nodeIds: string[]
    collapsedByDefault: boolean
    advisoryOnly?: boolean
  }>
  nodes: CurriculumGraphNode[]
  edges: CurriculumGraphEdge[]
  electiveBuckets?: ElectiveBucket[]
  advisories?: Array<{ code: string; severity: string; message: string }>
  bottlenecks: Array<{ courseNumber: string; blockedBy: string[]; reason: string }>
  /** Same course under different track catalog codes (from vault). */
  crossTrackEquivalenceGroups?: string[][]
  /** Parallel courses with no additional credit (מקצועות ללא זיכוי נוסף). */
  catalogOverlapEquivalenceGroups?: string[][]
  transcriptSummary?: {
    completedCount: number
    failedCount: number
    inProgressCount: number
  }
}

export type CourseOffering = {
  courseNumber: string
  academicYear: number
  semesterCode: number
  semesterName?: string
  scheduleGroups: Array<Record<string, string>>
  instructors?: string
  examDates?: Record<string, string | null>
}

export type CourseDetail = CourseSummary & {
  institutionId?: string
  syllabus?: string
  prerequisitesText?: string
  corequisitesText?: string
  noAdditionalCreditText?: string
  instructors?: string
  notes?: string
  offerings?: CourseOffering[]
}

export type SelectedLessonEvent = {
  eventId: string
  type: string
  group?: string | null
}

export type SelectedGroups = {
  lecture?: number | string | string[] | null
  tutorial?: number | string | string[] | null
  lab?: number | string | string[] | null
  project?: number | string | string[] | null
}

export type CustomEvent = {
  id?: string
  title: string
  day: string
  startTime: string
  endTime: string
  notes?: string
  color?: string
}

export type ExamSummaryItem = {
  courseNumber: string
  courseName?: string
  moed?: string | null
  date?: string | null
  startTime?: string | null
  endTime?: string | null
  raw?: string | null
  isMissing?: boolean
}

export type ExamSummary = {
  exams: ExamSummaryItem[]
  warnings?: Array<{
    type?: string
    date?: string
    courseNumbers?: string[]
    courseNumber?: string
    message?: string
  }>
  totalExams?: number
  missingCount?: number
}
export type PlannerInsights = {
  totalCredits?: number
  activeCourseCount?: number
  totalCourseCount?: number
  maxCreditsPerSemester?: number
  creditsWarning?: {
    status?: string
    message?: string
    totalCredits?: number
    maxCreditsPerSemester?: number
  }
  courseWarnings?: Array<{
    courseId?: string
    courseNumber?: string
    status?: string
    message?: string
    prerequisitesText?: string
    missingPrerequisiteNumbers?: string[]
  }>
  scheduleConflicts?: WeeklySchedule['conflicts']
  scheduleStatus?: string
  examSummary?: ExamSummary
  staleCourseWarnings?: Array<{
    courseNumber?: string
    courseId?: string
    status?: string
    message?: string
  }>
  lessonSelectionWarnings?: Array<{
    courseNumber?: string
    courseId?: string
    type?: string
    eventId?: string
    message?: string
  }>
}

export type ScheduleSlot = {
  day: string
  timeRange: string
  slotType?: string
  courseNumber?: string
  courseTitle?: string
}

export type WeeklySchedule = {
  status?: string
  entries?: Array<{
    courseId: string
    courseNumber?: string
    courseTitle?: string
    academicYear?: number
    semesterCode?: number
    scheduleGroups?: Array<Record<string, string>>
  }>
  conflicts?: Array<{
    day?: string
    timeRange?: string
    courseNumbers?: string[]
    reason?: string
  }>
  weekView?: Array<{ day: string; slots: ScheduleSlot[] }>
  summary?: string
  customEvents?: CustomEvent[]
}

export type PlannedCourse = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  credits?: number
  category?: string
  reason?: string
  isActive?: boolean
  selectedGroups?: SelectedGroups
  selectedLessonEvents?: SelectedLessonEvent[]
  notes?: string
}

export type SemesterPlan = {
  id: string
  name?: string
  status: string
  version: number
  plannerType: string
  semesters: Array<{
    semesterCode: string
    goalCredits?: number
    plannedCourses: PlannedCourse[]
    maybeCourses?: PlannedCourse[]
    weeklySchedule?: WeeklySchedule
    customEvents?: CustomEvent[]
  }>
  explanation?: {
    summary?: string
    partialPlan?: boolean
    emptyPlan?: boolean
    totalRecommendedCredits?: number
  }
  plannerInsights?: PlannerInsights
  shareEnabled?: boolean
  shareToken?: string | null
  readOnly?: boolean
}

export type AcademicRiskAnalysis = {
  id: string
  planId?: string | null
  semesterCode?: string
  analyzerType?: string
  analysisSource?: string
  status?: string
  summary?: {
    totalRisks: number
    highestSeverity: string | null
    counts: { low: number; medium: number; high: number }
  }
  risks?: Array<{
    riskType?: string
    severity?: string
    title?: string
    explanation?: string
  }>
}

export type AdvisorReply = {
  question: string
  answer: string
  confidence: 'high' | 'medium' | 'low' | string
  courseIds: string[]
  /** Same ids carrying their catalog/wiki display name, so a citation can read
   *  "E-Commerce Models" rather than "00960211". Optional: an older response
   *  shape has only `courseIds`. */
  courses?: { id: string; name: string }[]
  wikiSlugs: string[]
  sources: string[]
  contacts: string[]
  eligibility?: Record<string, unknown> | null
  semesterResolution?: Record<string, unknown> | null
  retrievalStatus?: string | null

}


// ---------------------------------------------------------------------------
// Browsable planner rows
// ---------------------------------------------------------------------------

/** Three separate sources, kept apart because they answer different questions:
 *  what students SCORED at scale, what they THOUGHT, and what our own
 *  transcripts hold. Coverage differs sharply between them. */
export type CourseSignal = {
  courseNumber: string
  /** From transcripts we hold. */
  cohort?: {
    sampleSize: number
    meanGrade: number
    passRate: number
  } | null
  /** CheeseFork reviews. `meanDifficultyRank` is higher = HARDER. */
  reviews?: {
    responseCount: number
    meanGeneralRank: number
    meanDifficultyRank: number
    scaleMax: number
    source?: string
  } | null
  /** Published Technion grade distributions. */
  published?: {
    termCount: number
    students: number
    passRate: number
    minGrade: number
    maxGrade: number
    averageGrade: number
    /** The mean of each term's median: a true pooled median is not published. */
    medianOfTermMedians: number
    source?: string
  } | null
}

/** Why a course was placed where it was, as a stable key the UI translates. */
export type ShelfReason =
  | 'closes_requirement'
  | 'offered_once_a_year'
  | 'unlocks_later_courses'
  | 'well_reviewed'
  | 'matches_your_electives'

export type ShelfEligibility = {
  status: 'eligible' | 'missing_prerequisites' | 'unknown'
  /** Each entry is one set of courses that would satisfy the requirement. */
  missingOptions: string[][]
}

/** What postponing a required course costs. Present on mandatory rows only. */
export type ShelfDeferral = {
  offeredOncePerYear: boolean
  nextOffering: { academicYear: number; semesterCode: number } | null
  termsUntilNextOffering: number | null
  dependentCount: number
  dependentCourseNumbers: string[]
  /** 37% of the catalog states no prerequisites, so zero means "none recorded". */
  dependentCountIsLowerBound: boolean
}

/** The student's weakest grade among prerequisites they actually took. */
export type ShelfReadiness = {
  weakestPrerequisiteCourse: string
  weakestPrerequisiteGrade: number
}

export type ShelfCourse = {
  /** Catalog id. Null for a required course the catalog does not carry. */
  id: string | null
  courseNumber: string
  title?: string | null
  titleHebrew?: string | null
  credits?: number | null
  faculty?: string | null
  offeredThisTerm: boolean
  eligibility: ShelfEligibility
  signal?: CourseSignal | null
  readiness?: ShelfReadiness | null
  unlocks: { count: number; courseNumbers: string[] }
  retakeClashesWithDraft: boolean
  requiresManualRegistration: boolean
  catalogKnown: boolean
  reasons: ShelfReason[]
  deferral?: ShelfDeferral
}

/** A course this row covers that simply does not run this term. */
export type ShelfLaterCourse = {
  courseNumber: string
  title?: string | null
  credits?: number | null
  nextOffering: { academicYear: number; semesterCode: number } | null
}

export type CourseShelf = {
  shelfId: string
  title: string
  /** `mandatory` is a checklist of timing; the others are menus. */
  kind: 'mandatory' | 'pool' | 'open'
  requirementGroupId: string
  requirementTitle: string
  creditsRemaining: number
  isChoice: boolean
  startedCount: number
  poolSize: number
  /** The bucket cannot be satisfied without drawing from this pool. */
  isRequiredPool: boolean
  /** For a `choose_n` pool, courses needed rather than credits. */
  stepsRequired: number | null
  stepsCompleted: number | null
  courses: ShelfCourse[]
  laterCourses: ShelfLaterCourse[]
  candidateCount: number
  notOfferedCount: number
  ineligibleCount: number
  noAdditionalCreditCount: number
  conflictsWithDraftCount: number
  wrongDegreeLevelCount: number
  emptyReason: 'pool_exhausted' | 'none_offered_this_term' | 'none_available_to_you' | null
}

export type DraftSummary = {
  plannedCourseCount: number
  plannedCredits: number
  difficulty: {
    plannedMean: number
    yourCompletedMean: number | null
    heavierThanUsual: boolean | null
    ratedCourses: number
    plannedCourses: number
    scaleMin: number
    scaleMax: number
  } | null
  exams: {
    examCount: number
    withoutPublishedExam: number
    tightestGapDays: number | null
    tightestPair: string[] | null
    firstExam: string | null
    lastExam: string | null
  } | null
}

export type CourseShelvesResponse = {
  semesterCode: string
  shelves: CourseShelf[]
  draftSummary: DraftSummary
}
