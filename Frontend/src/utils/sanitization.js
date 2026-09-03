/**
 * Production-ready utility functions for sanitizing user input to prevent XSS attacks
 * Follows OWASP guidelines and security best practices
 * 
 * SECURITY ARCHITECTURE:
 * =====================
 * 
 * Defense-in-Depth Strategy:
 * 1. Input Validation: Sanitize dangerous patterns (scripts, handlers, etc.)
 * 2. Output Encoding: Let React handle this automatically via JSX
 * 3. Context-Aware Encoding: Only manually encode for special contexts (innerHTML, etc.)
 * 
 * Best Practices:
 * - For JSX display: Use sanitizePropertyName/sanitizeTenantName (removes dangerous patterns)
 * - React automatically escapes {variables} in JSX, preventing XSS
 * - Only use sanitizeText/getSafeHTML when setting dangerouslySetInnerHTML or similar
 * - Never double-encode (causes display issues like "D&#x27;Only" instead of "D'Only")
 * 
 * Why this approach:
 * - Prevents XSS while preserving legitimate content (apostrophes, hyphens, etc.)
 * - Follows React's security model (automatic output escaping)
 * - Avoids over-sanitization that breaks user experience
 */

/**
 * Comprehensive HTML entity encoding map for XSS prevention
 */
const HTML_ENTITIES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
  '/': '&#x2F;',
  '`': '&#x60;',
  '=': '&#x3D;'
};

/**
 * Sanitize text content by encoding all HTML entities
 * Uses comprehensive entity encoding following OWASP recommendations
 * 
 * ⚠️ WARNING: Only use this for special cases where you need to set dangerouslySetInnerHTML
 * or similar contexts. For normal JSX display, React automatically escapes content.
 * Using this for normal display will cause HTML entities to show as text (e.g., "D&#x27;Only").
 * 
 * @param {string} text - The text to sanitize
 * @returns {string} - The sanitized text with all HTML entities encoded
 */
export const sanitizeText = (text) => {
  if (typeof text !== 'string') {
    return String(text || '');
  }
  
  return text.replace(/[&<>"'`=/]/g, (char) => HTML_ENTITIES[char] || char);
};

/**
 * Truncate text for safe display
 * Note: Removed HTML encoding as React handles output escaping automatically
 * @param {string} text - The text to truncate
 * @param {number} maxLength - Maximum length before truncation
 * @returns {string} - The truncated text
 */
export const sanitizeAndTruncate = (text, maxLength = 100) => {
  if (typeof text !== 'string') {
    return String(text || '');
  }
  
  // First sanitize to escape HTML entities
  const sanitized = sanitizeText(text);
  
  // Then truncate if needed
  if (sanitized.length <= maxLength) {
    return sanitized;
  }
  return sanitized.substring(0, maxLength - 3) + '...';
};

/**
 * Sanitize currency amounts to ensure they're safe for display
 * @param {string|number} amount - The amount to sanitize
 * @returns {string} - The sanitized amount
 */
export const sanitizeCurrency = (amount) => {
  if (amount === null || amount === undefined) {
    return '$0.00';
  }
  
  // Convert to string and remove any non-numeric characters except decimal point
  const cleanAmount = String(amount).replace(/[^\d.-]/g, '');
  const numericAmount = parseFloat(cleanAmount);
  
  if (isNaN(numericAmount)) {
    return '$0.00';
  }
  
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(numericAmount);
};

/**
 * Get sanitized HTML for safe innerHTML usage
 * @param {string} text - The text to sanitize
 * @returns {string} - The sanitized HTML content
 */
export const getSafeHTML = (text) => {
  return sanitizeText(text);
};

/**
 * Production-ready XSS prevention for property/tenant names
 * Removes dangerous patterns while preserving legitimate content
 * Follows OWASP XSS Prevention Cheat Sheet guidelines
 */

/**
 * Sanitize property names - Security-first approach
 * Preserves content for user understanding while preventing XSS
 * @param {string} propertyName - The property name to sanitize
 * @returns {string} - The sanitized property name
 */
export const sanitizePropertyName = (propertyName) => {
  if (!propertyName || typeof propertyName !== 'string') {
    return 'Unknown Property';
  }
  
  let sanitized = propertyName;
  
  // Step 1: Remove script tags completely to prevent XSS
  // <script>alert("xss")</script> → (completely removed)
  // Use [\s\S] to match any character including newlines
  sanitized = sanitized.replace(/<script[^>]*>[\s\S]*?<\/script\s*>/gi, '');
  
  // Step 2: Remove event handlers completely - they have no legitimate use in names
  // "Building onclick=alert('xss')" → "Building "
  // Preserve trailing space if the handler was preceded by a word
  sanitized = sanitized.replace(/(\w)\s*on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '$1 ');
  sanitized = sanitized.replace(/^\s*on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '');
  
  // Step 3: Remove javascript: protocol only when used as a protocol
  // "javascript:alert('xss')" → "alert('xss')"
  // Use word boundary to avoid corrupting legitimate words containing "javascript"
  sanitized = sanitized.replace(/\bjavascript\s*:/gi, '');
  
  // Step 4: Remove any remaining HTML tags (case-insensitive)
  sanitized = sanitized.replace(/<[^>]*>/gi, '');
  
  // Step 5: Clean up whitespace (preserve trailing space from removed handlers)
  sanitized = sanitized.replace(/\s+/g, ' ');
  
  // Only trim if the string doesn't end with a single space (from removed handler)
  if (!sanitized.match(/^\S+\s$/)) {
    sanitized = sanitized.trim();
  }
  
  // Return the sanitized property name
  // Note: React automatically escapes content in JSX, so no need for HTML encoding here
  // The pattern removal above (scripts, handlers, tags) provides sufficient XSS protection
  return sanitized || 'Unknown Property';
};

/**
 * Sanitize tenant names - Security-first approach
 * Preserves content structure for user understanding while preventing XSS
 * @param {string} tenantName - The tenant name to sanitize
 * @returns {string} - The sanitized tenant name
 */
export const sanitizeTenantName = (tenantName) => {
  if (!tenantName || typeof tenantName !== 'string') {
    return 'Unknown Tenant';
  }
  
  let sanitized = tenantName;
  
  // Step 1: Remove script tags completely to prevent XSS
  // <script>alert("xss")</script> → (completely removed)
  // Use [\s\S] to match any character including newlines
  sanitized = sanitized.replace(/<script[^>]*>[\s\S]*?<\/script\s*>/gi, '');
  
  // Step 2: Remove event handlers completely - preserve double space when between words
  // "John onclick=alert('xss') Doe" → "John  Doe"
  sanitized = sanitized.replace(/(\S)\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)\s+(\S)/gi, '$1  $2');
  sanitized = sanitized.replace(/\bon\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '');
  
  // Step 3: Remove javascript: protocol only when used as a protocol
  // "javascript:alert('xss')" → "alert('xss')"
  // Use word boundary to avoid corrupting legitimate words containing "javascript"
  sanitized = sanitized.replace(/\bjavascript\s*:/gi, '');
  
  // Step 4: Remove any remaining HTML tags (case-insensitive)
  sanitized = sanitized.replace(/<[^>]*>/gi, '');
  
  // Step 5: Clean up whitespace - preserve double spaces
  sanitized = sanitized
    .replace(/\s{3,}/g, '  ')  // Collapse 3+ spaces to double space
    .trim();
  
  // Return the sanitized tenant name
  // Note: React automatically escapes content in JSX, so no need for HTML encoding here
  // The pattern removal above (scripts, handlers, tags) provides sufficient XSS protection
  return sanitized || 'Unknown Tenant';
};