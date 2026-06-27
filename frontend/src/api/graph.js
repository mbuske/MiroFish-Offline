import service, { requestWithRetry } from './index'

/**
 * Generate ontology (upload documents and simulation requirements)
 * @param {Object} data - Contains files, simulation_requirement, project_name, etc.
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Build graph
 * @param {Object} data - Contains project_id, graph_name, etc.
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Query task status
 * @param {String} taskId - Task ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Get graph data
 * @param {String} graphId - Graph ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Get project information
 * @param {String} projectId - Project ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * Save a human-edited ontology (Step 01 pause gate).
 * @param {string} projectId
 * @param {{ontology: object, analysis_summary?: string}} payload
 */
export function saveOntology(projectId, payload) {
  return requestWithRetry(() =>
    service({ url: `/api/graph/project/${projectId}/ontology`, method: 'put', data: payload })
  )
}

export function updateNode(graphId, uuid, fields) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/node/${uuid}`, method: 'patch', data: fields }))
}
export function deleteNode(graphId, uuid) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/node/${uuid}`, method: 'delete' }))
}
export function updateEdge(graphId, edgeUuid, fields) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/edge/${edgeUuid}`, method: 'patch', data: fields }))
}
export function deleteEdge(graphId, edgeUuid) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/edge/${edgeUuid}`, method: 'delete' }))
}
export function mergeNodes(graphId, primary, duplicates) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/merge`, method: 'post', data: { primary, duplicates } }))
}
