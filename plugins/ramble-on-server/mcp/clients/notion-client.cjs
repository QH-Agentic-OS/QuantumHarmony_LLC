/**
 * mcp/clients/notion-client.cjs
 *
 * Notion REST client used by the KB tools. Owns the API base URL, version
 * header, and auth. All KB operations go through `notionRequest()`.
 */

'use strict';

const https = require('https');
const { CONFIG, requireNotionToken, getRootPage } = require('../env.cjs');

/**
 * Sends an authenticated request to the Notion API.
 *
 * @param {string} method The HTTP method to send.
 * @param {string} endpoint The Notion API path beginning with `/`.
 * @param {object | null} [body=null] The optional JSON body to serialize.
 * @returns {Promise<object>} The parsed Notion API response body.
 */
const notionRequest = (method, endpoint, body = null) => {
  const token = requireNotionToken();
  const url = `${CONFIG.notion.apiBase}${endpoint}`;
  const options = {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Notion-Version': CONFIG.notion.version,
      'Content-Type': 'application/json',
    },
  };

  return new Promise((resolve, reject) => {
    const req = https.request(url, options, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (
            res.statusCode < 200 ||
            res.statusCode >= 300 ||
            parsed.object === 'error'
          ) {
            reject(
              new Error(
                parsed.message ||
                  `Notion API returned status ${res.statusCode}`,
              ),
            );
          } else {
            resolve(parsed);
          }
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
};

/**
 * Extracts the human-readable title from a Notion page object.
 *
 * @param {object} page The Notion page payload.
 * @returns {string} The page title or 'Untitled' when missing.
 */
const extractPageTitle = (page) =>
  page?.properties?.title?.title?.[0]?.plain_text ||
  page?.properties?.Name?.title?.[0]?.plain_text ||
  'Untitled';

/**
 * Search the Notion KB for pages relevant to a query.
 *
 * @param {{query: string, max_results?: number}} params The search query and
 * optional result limit.
 * @returns {Promise<{pages: Array<object>, query: string}>} The matched pages
 * and the original query text.
 */
const kbSearch = async ({ query, max_results = 5 }) => {
  const result = await notionRequest('POST', '/search', {
    query,
    filter: { property: 'object', value: 'page' },
    page_size: max_results,
  });

  const pages = (result.results || []).map((page) => ({
    id: page.id,
    title: extractPageTitle(page),
    url: page.url,
    last_edited: page.last_edited_time,
  }));

  return { pages, query };
};

/**
 * Finds the first page the caller can see whose title contains `text`
 * (case-insensitive). Used when no Ramble On root page is configured, as with
 * a Notion sign-in, where the user picks which pages to share.
 *
 * @param {string} text
 * @returns {Promise<{id: string, title: string} | null>}
 */
const findPageByTitle = async (text) => {
  const result = await notionRequest('POST', '/search', {
    query: text,
    filter: { property: 'object', value: 'page' },
    page_size: 10,
  });
  const wanted = text.toLowerCase();
  const page = (result.results || []).find((p) =>
    extractPageTitle(p).toLowerCase().includes(wanted),
  );
  return page ? { id: page.id, title: extractPageTitle(page) } : null;
};

/**
 * Fetches all child blocks of a Notion page, automatically paginating through
 * multiple pages of results when the page has more than 100 blocks.
 *
 * @param {string} page_id The Notion page identifier to fetch blocks for.
 * @returns {Promise<Array<object>>} All child block results.
 */
const fetchAllBlocks = async (page_id) => {
  const allResults = [];
  let cursor;
  do {
    const endpoint = cursor
      ? `/blocks/${page_id}/children?page_size=100&start_cursor=${encodeURIComponent(cursor)}`
      : `/blocks/${page_id}/children?page_size=100`;
    const response = await notionRequest('GET', endpoint);
    allResults.push(...(response.results || []));
    cursor = response.has_more ? response.next_cursor : undefined;
  } while (cursor);
  return allResults;
};

/**
 * Fetch the full content of a Notion page by ID.
 *
 * @param {{page_id: string}} params The Notion page identifier to fetch.
 * @returns {Promise<{title: string, body: string, page_id: string, url: string}>}
 * The page title, flattened body text, source id, and URL.
 */
const kbFetchPage = async ({ page_id }) => {
  const [page, blockResults] = await Promise.all([
    notionRequest('GET', `/pages/${page_id}`),
    fetchAllBlocks(page_id),
  ]);

  const title = extractPageTitle(page);

  const extractText = (block) => {
    const type = block.type;
    const content = block[type];
    if (!content?.rich_text) return '';
    return content.rich_text.map((rt) => rt.plain_text).join('');
  };

  const bodyText = blockResults
    .map(extractText)
    .filter(Boolean)
    .join('\n');

  return { title, body: bodyText, page_id, url: page.url };
};

/**
 * Write or append content to a Notion KB page.
 *
 * @param {{page_id?: string, title?: string, content: string, mode?: string}}
 * params The page target, optional title, content payload, and write mode.
 * @returns {Promise<object>} The write result including success state and page
 * metadata.
 */
const kbWrite = async ({ page_id, title, content, mode = 'append' }) => {
  if (page_id && mode === 'append') {
    await notionRequest('PATCH', `/blocks/${page_id}/children`, {
      children: [
        {
          object: 'block',
          type: 'paragraph',
          paragraph: {
            rich_text: [{ type: 'text', text: { content } }],
          },
        },
      ],
    });
    return { success: true, mode: 'appended', page_id };
  }

  if (title) {
    const newPage = await notionRequest('POST', '/pages', {
      parent: { page_id: page_id || (await resolveParentPage()) },
      properties: {
        title: { title: [{ type: 'text', text: { content: title } }] },
      },
      children: content
        ? [
            {
              object: 'block',
              type: 'paragraph',
              paragraph: {
                rich_text: [{ type: 'text', text: { content } }],
              },
            },
          ]
        : [],
    });
    return {
      success: true,
      mode: 'created',
      page_id: newPage.id,
      url: newPage.url,
    };
  }

  throw new Error(
    'kbWrite requires either page_id (to append) or title (to create).',
  );
};

/**
 * Returns the page that kb_write creates new pages under: the configured
 * root page, or else a shared page titled "Ramble On".
 *
 * @returns {Promise<string>} The parent page ID.
 */
const resolveParentPage = async () => {
  if (getRootPage()) return getRootPage();
  const page = await findPageByTitle('Ramble On');
  if (page) return page.id;
  throw new Error(
    'No parent page for the new page. Pass page_id, set the Ramble On root page in the plugin settings, or share a page titled "Ramble On" with Ramble On.',
  );
};


/**
 * Get the user's voice model from Notion.
 *
 * @returns {Promise<object>} The voice-model lookup result and page content
 * when found.
 */
const getVoiceModel = async () => {
  let voicePage = null;
  if (getRootPage()) {
    const allBlocks = await fetchAllBlocks(getRootPage());
    voicePage = allBlocks.find(
      (block) =>
        block.type === 'child_page' &&
        block.child_page?.title?.toLowerCase().includes('voice model'),
    );
  } else {
    // No root page configured: look through the pages shared with Ramble On.
    voicePage = await findPageByTitle('Voice Model');
  }

  if (!voicePage) {
    return {
      found: false,
      message:
        'No Voice Model page found in Notion KB. Run init to scaffold one.',
    };
  }

  const content = await kbFetchPage({ page_id: voicePage.id });
  return { found: true, ...content };
};

module.exports = {
  notionRequest,
  kbSearch,
  kbFetchPage,
  kbWrite,
  getVoiceModel,
};
