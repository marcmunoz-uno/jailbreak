/**
 * Job classifier for template-based query routing.
 * Classifies queries into job types for template selection.
 */

export type JobType = 'default' | 'code' | 'analysis' | 'creative'

export type ClassificationResult = {
  jobType: JobType
  confidence: number
}

/**
 * Classify a query string into a job type for template routing.
 */
export function classifyJob(_query: string): ClassificationResult {
  return { jobType: 'default', confidence: 1.0 }
}
