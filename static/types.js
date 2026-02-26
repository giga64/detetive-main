/**
 * TypeScript Types (JSDoc)
 * 
 * Uso em arquivos .js:
 * /// <reference path="types.js" />
 */

/**
 * @typedef {Object} ConsultaResult
 * @property {'cpf' | 'cnpj' | 'oab' | 'placa' | 'nome'} tipo
 * @property {Object} dados
 * @property {number} confianca - 0-100
 * @property {string} fonte
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} DadosPessoais
 * @property {string} nome
 * @property {string} cpf
 * @property {number} idade
 * @property {string} profissao
 * @property {Array<string>} enderecos
 * @property {Array<string>} telefones
 */

/**
 * @typedef {Object} DadosEmpresa
 * @property {string} razao_social
 * @property {string} cnpj
 * @property {string} matriz_filial
 * @property {Date} data_abertura
 * @property {string} natureza_juridica
 * @property {string} endereco
 */

/**
 * @typedef {Object} WebVitalMetric
 * @property {number} value
 * @property {'good' | 'poor'} status
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} Metrics
 * @property {WebVitalMetric} lcp - Largest Contentful Paint
 * @property {WebVitalMetric} fid - First Input Delay
 * @property {WebVitalMetric} cls - Cumulative Layout Shift
 * @property {number} ttl - Time to Interactive
 * @property {Object} navigationTiming
 */

/**
 * @typedef {Object} JourneyEvent
 * @property {'click' | 'consulta_iniciada' | 'resultado_visivel' | 'conversao'} event
 * @property {Object} [data]
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} ErrorLog
 * @property {'js_error' | 'unhandled_promise' | 'fetch_error'} type
 * @property {string} message
 * @property {string} [stack]
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} ObservabilityPayload
 * @property {string} sessionId
 * @property {string} userAgent
 * @property {string} url
 * @property {Metrics} metrics
 * @property {Array<ErrorLog>} errors
 * @property {Array<JourneyEvent>} journey
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} ConversionEvent
 * @property {string} sessionId
 * @property {'consulta' | 'download' | 'share' | 'report'} type
 * @property {number} value
 * @property {Date} timestamp
 */

/**
 * @typedef {Object} APIResponse
 * @property {boolean} success
 * @property {Object} data
 * @property {string} [error]
 * @property {string} [message]
 */

// Exportar para uso em TypeScript/JSDoc
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {};
}
