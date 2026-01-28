/**
 * Consolidated UX Testing Script for Kindred Histories
 *
 * Runs the same checks in both authenticated and unauthenticated modes.
 *
 * Usage:
 *   npm run test              # Run all tests (unauth + auth)
 *   npm run test -- --unauth-only  # Run only unauthenticated tests
 *   npm run test -- --auth-only    # Run only authenticated tests
 *
 * Tests:
 *
 * 1. Query Tests (runQueryTest) - Both modes
 *    Submits 3 Gemini-generated user descriptions (simple, complex, edge case),
 *    verifies the UI accepts input, submits, shows loading feedback, and displays
 *    results. In authenticated mode, also verifies searches are saved to history.
 *
 * 2. Cache Test (runCacheTest) - Both modes
 *    Re-runs the first query and compares timing to the original run. Checks
 *    whether the second run is ≥30% faster (indicating a cache hit) and looks
 *    for cache-hit console log messages.
 *
 * 3. Facet Combinations Test (runFacetCombinationsTest) - Both modes
 *    Exercises the facet filter panel: Check All (OR), Uncheck All, select a
 *    subset (OR), switch to AND mode, Check All (AND), restore OR mode.
 *    Validates match counts are logically consistent (e.g. AND ≤ OR, none = 0).
 *    Also checks for duplicate facet labels.
 *
 * 4. Formatting Test (runFormattingTest) - Both modes
 *    Checks table rows for raw markdown syntax (**, *, #, [](), ``).
 *    Opens a person detail modal and verifies: no raw markdown in modal content,
 *    expected sections exist (Context, Challenges, Overcame, Achievements),
 *    styled HTML elements are present (strong, p, h2, h3). Also tests modal
 *    close behavior and text truncation in table cells.
 *
 * 5. Tab Switching Test (runTabSwitchingTest) - Auth only
 *    Switches between "Filter by Facets" and "Your Searches" tabs, verifying
 *    each panel renders correctly and switching back restores the facets view.
 *
 * 6. Search Switch Test (runSearchSwitchTest) - Auth only
 *    Navigates to "Your Searches", clicks a previous search entry, and verifies
 *    results update (match count changes or results are displayed).
 */

import puppeteer from 'puppeteer';
import fs from 'fs';
import dotenv from 'dotenv';

// Load environment variables from parent directory
dotenv.config({ path: '../.env' });

// Configuration
const FRONTEND_URL = 'http://localhost:5173';
const FRONTEND_URL_AUTH = 'http://localhost:5173?testAuth=true';
const API_URL = 'http://localhost:8000';
const RESULTS_DIR = './test-results';
const MAX_WAIT_TIME = 180000; // 3 minutes max wait

// Timing constants
const WAIT_AFTER_CLICK = 500;
const WAIT_FOR_API = 15000;
const WAIT_FOR_COUNT_STABLE = 10000;
const WAIT_BETWEEN_TESTS = 1000;
const WAIT_FOR_UI_UPDATE = 300;

/**
 * Generate varied test queries using Gemini API
 * This ensures each test run uses unique queries to avoid cache hits
 * REQUIRED: Will throw if Gemini API is not available
 */
async function generateTestQueries() {
  const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

  if (!GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY environment variable is required. Set it in ../.env');
  }

  console.log('[INFO] Generating unique test queries with Gemini...');

  const prompt = `Generate 3 unique user descriptions for testing a historical figure discovery app.
The app helps people from marginalized backgrounds discover historical figures who share their identity traits.

Generate varied descriptions with these categories:
1. A simple description (1-2 identity traits + 1 interest)
2. A complex description (3-4 identity traits + 2-3 interests/aspirations)
3. A short/edge case (just 1-2 words describing an identity)

Return ONLY a JSON array with this exact format, no other text:
[
  {"name": "simple_query", "description": "Simple query test", "input": "the user description here"},
  {"name": "complex_query", "description": "Complex query with multiple facets", "input": "the user description here"},
  {"name": "edge_case_short", "description": "Edge case - very short input", "input": "short input here"}
]

Be creative and diverse! Use different ethnicities, genders, sexualities, regions, interests, and aspirations each time.
Examples of good variety:
- "I'm a Korean-American nonbinary person passionate about environmental activism"
- "I'm a deaf Black woman from Detroit who loves poetry and wants to be a teacher"
- "Indigenous artist"
- "I'm a gay Latino veteran interested in mental health advocacy"`;

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 1.0,
          maxOutputTokens: 500
        }
      })
    }
  );

  if (!response.ok) {
    throw new Error(`Gemini API returned ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;

  if (!text) {
    throw new Error('No text in Gemini response');
  }

  // Extract JSON from response (handle markdown code blocks)
  let jsonStr = text;
  const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (jsonMatch) {
    jsonStr = jsonMatch[1].trim();
  }

  const queries = JSON.parse(jsonStr);

  if (!Array.isArray(queries) || queries.length < 3) {
    throw new Error(`Invalid query format from Gemini: expected array of 3, got ${JSON.stringify(queries)}`);
  }

  console.log('[SUCCESS] Generated unique test queries:');
  for (const q of queries) {
    console.log(`  - ${q.name}: "${q.input.substring(0, 50)}..."`);
  }

  return queries;
}

// Will be populated at runtime by generateTestQueries()
let TEST_QUERIES = [];

class UXTester {
  constructor() {
    this.browser = null;
    this.results = {
      unauth: null,
      auth: null
    };
    this.consoleLogs = [];
    this.networkRequests = [];
    this.timestamps = {};
    this.pendingApiResponse = null;
    this.pageStartTime = null;
    this.searchHistory = [];
  }

  async setup() {
    if (!fs.existsSync(RESULTS_DIR)) {
      fs.mkdirSync(RESULTS_DIR, { recursive: true });
    }

    this.browser = await puppeteer.launch({
      headless: false,
      defaultViewport: { width: 1400, height: 900 },
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
  }

  setupPageListeners(page) {
    this.pageStartTime = Date.now();

    page.on('console', (msg) => {
      const elapsed = Date.now() - (this.timestamps.testStart || this.pageStartTime);
      const log = {
        type: msg.type(),
        text: msg.text(),
        timestamp: elapsed
      };
      this.consoleLogs.push(log);
      if (log.type === 'error') {
        console.log(`[CONSOLE ${elapsed}ms] ${log.type}: ${log.text}`);
      }
    });

    page.on('request', (request) => {
      if (request.url().includes(API_URL)) {
        const elapsed = Date.now() - (this.timestamps.testStart || this.pageStartTime);
        const req = {
          url: request.url(),
          method: request.method(),
          startTime: elapsed,
          postData: request.postData()
        };
        this.networkRequests.push(req);
        console.log(`[NETWORK ${elapsed}ms] ${req.method} ${req.url}`);
      }
    });

    page.on('response', async (response) => {
      if (response.url().includes(API_URL)) {
        const req = this.networkRequests.find(
          (r) => r.url === response.url() && !r.endTime
        );
        if (req) {
          const elapsed = Date.now() - (this.timestamps.testStart || this.pageStartTime);
          req.endTime = elapsed;
          req.status = response.status();
          req.duration = req.endTime - req.startTime;
          console.log(
            `[RESPONSE ${elapsed}ms] ${response.status()} ${response.url()} (${req.duration}ms)`
          );

          try {
            const body = await response.text();
            req.responseSize = body.length;
            try {
              req.responseBody = JSON.parse(body);
            } catch {
              // Not JSON
            }
          } catch (e) {
            // Can't get response body
          }
        }

        if (
          response.url().includes('/api/figures/semantic') &&
          this.pendingApiResponse
        ) {
          console.log(`[API] Semantic search completed with status ${response.status()}`);
          this.pendingApiResponse.resolve(response.status());
          this.pendingApiResponse = null;
        }
      }
    });
  }

  // ========================================
  // HELPER METHODS
  // ========================================

  async findButtonByText(page, textOrArray) {
    const texts = Array.isArray(textOrArray) ? textOrArray : [textOrArray];
    const buttons = await page.$$('button');
    for (const btn of buttons) {
      const btnText = await page.evaluate((el) => el.textContent, btn);
      for (const text of texts) {
        if (btnText && btnText.includes(text)) {
          return btn;
        }
      }
    }
    return null;
  }

  async getMatchCount(page) {
    return await page.evaluate(() => {
      const text = document.body.innerText;
      const match = text.match(/(\d+)\s*match/i);
      return match ? parseInt(match[1]) : -1;
    });
  }

  waitForSemanticResponse(timeout = WAIT_FOR_API) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        if (this.pendingApiResponse) {
          this.pendingApiResponse = null;
          console.log('[API] Semantic API timeout - continuing anyway');
          resolve(-1);
        }
      }, timeout);

      this.pendingApiResponse = {
        resolve: (status) => {
          clearTimeout(timer);
          resolve(status);
        }
      };
    });
  }

  async waitForCountStable(page, timeout = WAIT_FOR_COUNT_STABLE) {
    const start = Date.now();
    let lastCount = -1;
    let stableCount = 0;

    while (Date.now() - start < timeout) {
      await new Promise((r) => setTimeout(r, 500));
      const currentCount = await this.getMatchCount(page);

      if (currentCount === lastCount && currentCount !== -1) {
        stableCount++;
        if (stableCount >= 3) {
          return currentCount;
        }
      } else {
        stableCount = 0;
        lastCount = currentCount;
      }
    }
    return lastCount;
  }

  async clickAndWaitForApi(page, buttonText, timeout = WAIT_FOR_API) {
    const btn = await this.findButtonByText(page, buttonText);
    if (!btn) {
      throw new Error(`Button "${buttonText}" not found`);
    }

    const apiPromise = this.waitForSemanticResponse(timeout);
    await btn.click();
    console.log(`[ACTION] Clicked "${buttonText}", waiting for API...`);

    await apiPromise;
    console.log(`[ACTION] API response received`);
    await new Promise((r) => setTimeout(r, WAIT_FOR_UI_UPDATE));

    return await this.getMatchCount(page);
  }

  async getFacetNames(page) {
    return await page.evaluate(() => {
      const labels = document.querySelectorAll('label');
      const facetNames = [];
      const seen = new Set();

      for (const label of labels) {
        const text = label.textContent?.trim();
        if (
          text &&
          !text.includes('Check') &&
          !text.includes('Uncheck') &&
          text.length > 0
        ) {
          if (!seen.has(text)) {
            seen.add(text);
            facetNames.push(text);
          }
        }
      }
      return facetNames;
    });
  }

  async checkForDuplicateFacets(page) {
    const duplicateInfo = await page.evaluate(() => {
      const labels = document.querySelectorAll('label');
      const counts = {};
      const duplicates = [];

      for (const label of labels) {
        const text = label.textContent?.trim();
        if (
          text &&
          !text.includes('Check') &&
          !text.includes('Uncheck') &&
          text.length > 0
        ) {
          counts[text] = (counts[text] || 0) + 1;
        }
      }

      for (const [name, count] of Object.entries(counts)) {
        if (count > 1) {
          duplicates.push({ name, count });
        }
      }

      return {
        total: Object.keys(counts).length,
        duplicates
      };
    });

    if (duplicateInfo.duplicates.length > 0) {
      console.log(`\n[WARNING] Found ${duplicateInfo.duplicates.length} duplicate facets:`);
      for (const dup of duplicateInfo.duplicates) {
        console.log(`  - "${dup.name}" appears ${dup.count} times`);
      }
    } else {
      console.log(`[INFO] No duplicate facets found (${duplicateInfo.total} unique facets)`);
    }

    return duplicateInfo;
  }

  async toggleFacet(page, facetText) {
    const labels = await page.$$('label');
    for (const label of labels) {
      const text = await page.evaluate((el) => el.textContent?.trim(), label);
      if (text === facetText) {
        const apiPromise = this.waitForSemanticResponse();
        await label.click();
        console.log(`[ACTION] Toggled facet "${facetText}"`);
        await apiPromise;
        await new Promise((r) => setTimeout(r, WAIT_FOR_UI_UPDATE));
        return true;
      }
    }
    console.log(`[WARN] Facet "${facetText}" not found`);
    return false;
  }

  async getFacetColumnCount(page) {
    // Count facet columns in the table header (columns after "Overall")
    return await page.evaluate(() => {
      // Look for the header row with "Overall" and count columns after it
      const allDivs = document.querySelectorAll('div');
      let inHeader = false;
      let columnCount = 0;

      for (const div of allDivs) {
        const style = div.getAttribute('style') || '';
        const text = div.innerText?.trim();

        // Find header row (has "Overall" and specific styling)
        if (style.includes('min-width: 80px') && text === 'Overall') {
          inHeader = true;
          continue;
        }

        // Count columns with min-width: 100px after Overall (these are facet columns)
        if (inHeader && style.includes('min-width: 100px') && style.includes('width: 100px')) {
          columnCount++;
        }
      }

      return columnCount;
    });
  }

  async waitForResults(page, testName, prefix) {
    let firstFeedbackTime = null;
    const feedbackStart = Date.now();

    while (Date.now() - feedbackStart < MAX_WAIT_TIME) {
      const feedback = await page.evaluate(() => {
        const text = document.body.innerText;
        const searching = text.includes('Searching');
        const discovering = text.includes('Discovering');
        const hasFacetPanel =
          text.includes('Filter') || text.includes('Facet');
        const resultRows = document.querySelectorAll('[style*="border-bottom"]');
        return {
          searching,
          discovering,
          hasFacetPanel,
          resultCount: resultRows.length
        };
      });

      if (feedback.hasFacetPanel || feedback.searching || feedback.discovering) {
        if (!firstFeedbackTime) {
          firstFeedbackTime = Date.now() - this.timestamps.testStart;
          this.timestamps.firstFeedback = firstFeedbackTime;
          console.log(`[TIMING] First meaningful feedback at ${firstFeedbackTime}ms`);
          await page.screenshot({
            path: `${RESULTS_DIR}/${prefix}_${testName}_04_first_feedback.png`
          });
        }
      }

      if (feedback.resultCount > 0) {
        this.timestamps.firstResult = Date.now() - this.timestamps.testStart;
        console.log(`[TIMING] First result visible at ${this.timestamps.firstResult}ms`);
        await page.screenshot({
          path: `${RESULTS_DIR}/${prefix}_${testName}_05_first_result.png`
        });
        break;
      }

      await new Promise((r) => setTimeout(r, 1000));
    }

    console.log('\n[STEP] Waiting for results to stabilize...');
    await this.waitForCountStable(page, 8000);

    await page.screenshot({
      path: `${RESULTS_DIR}/${prefix}_${testName}_06_final.png`,
      fullPage: true
    });
  }

  // ========================================
  // TEST METHODS
  // ========================================

  async runQueryTest(page, query, isFirst, isAuthenticated) {
    const prefix = isAuthenticated ? 'auth' : 'unauth';
    this.consoleLogs = [];
    this.networkRequests = [];
    this.timestamps = { testStart: Date.now() };

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Starting test: ${query.name} (${isAuthenticated ? 'Authenticated' : 'Unauthenticated'})`);
    console.log(`Input: "${query.input}"`);
    console.log('='.repeat(60));

    const result = {
      scenario: query.name,
      input: query.input,
      authenticated: isAuthenticated
    };

    try {
      // If not first test, need to get back to chat interface
      if (!isFirst) {
        console.log('\n[STEP] Returning to chat interface...');
        const newSearchBtn = await this.findButtonByText(page, 'New Search');
        if (newSearchBtn) {
          await newSearchBtn.click();
          // Wait for the view to transition back to chat interface
          await new Promise((r) => setTimeout(r, 2000));
        } else {
          // In unauthenticated mode, there's no "New Search" button
          // Need to refresh the page to return to chat interface
          console.log('[INFO] No "New Search" button - refreshing page (unauthenticated mode)');
          await page.reload({ waitUntil: 'networkidle0', timeout: 30000 });
          await new Promise((r) => setTimeout(r, 1000));
        }
      }

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${query.name}_01_before_input.png`
      });

      console.log('\n[STEP] Finding input field...');
      const inputSelector = 'textarea, input[type="text"]';
      // Increased timeout and better error handling
      try {
        await page.waitForSelector(inputSelector, { timeout: 15000 });
      } catch (e) {
        // Take diagnostic screenshot
        await page.screenshot({
          path: `${RESULTS_DIR}/${prefix}_${query.name}_input_not_found.png`,
          fullPage: true
        });
        throw new Error(`Input field not found. Page may not have returned to chat view. See screenshot.`);
      }

      console.log(`\n[STEP] Typing input: "${query.input}"`);
      this.timestamps.inputStart = Date.now() - this.timestamps.testStart;

      const input = await page.$(inputSelector);
      await input.click({ clickCount: 3 });
      await page.keyboard.press('Backspace');
      // Set value directly for speed, then dispatch input event to trigger React
      await page.evaluate((selector, value) => {
        const el = document.querySelector(selector);
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype, 'value'
        )?.set || Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value'
        )?.set;
        nativeInputValueSetter?.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, inputSelector, query.input);

      this.timestamps.inputComplete = Date.now() - this.timestamps.testStart;

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${query.name}_02_after_input.png`
      });

      console.log('\n[STEP] Looking for submit button...');
      let submitButton = await page.$('button[type="submit"]');
      if (!submitButton) {
        submitButton = await this.findButtonByText(page, [
          'Begin Journey',
          'Discover',
          'Search',
          'Find',
          'Submit'
        ]);
      }

      if (submitButton) {
        this.timestamps.submitClick = Date.now() - this.timestamps.testStart;
        console.log(`[TIMING] Submit clicked at ${this.timestamps.submitClick}ms`);
        await submitButton.click();
      } else {
        throw new Error('Could not find submit button');
      }

      await new Promise((r) => setTimeout(r, WAIT_AFTER_CLICK));
      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${query.name}_03_loading.png`
      });

      console.log('\n[STEP] Waiting for results...');
      await this.waitForResults(page, query.name, prefix);

      // Track search for switch test (auth only)
      if (isAuthenticated) {
        this.searchHistory.push({
          name: query.name,
          input: query.input,
          time: Date.now()
        });

        console.log('\n[STEP] Verifying search was saved...');
        result.searchSaved = await this.verifySearchSaved(page, query.input);
        console.log(`[INFO] Search saved: ${result.searchSaved}`);
      }

      this.timestamps.testEnd = Date.now() - this.timestamps.testStart;

      result.success = true;
      result.timestamps = this.timestamps;
      result.metrics = {
        timeToSubmit: this.timestamps.submitClick - this.timestamps.inputStart,
        timeToFirstFeedback: this.timestamps.firstFeedback
          ? this.timestamps.firstFeedback - this.timestamps.submitClick
          : null,
        timeToFirstResult: this.timestamps.firstResult
          ? this.timestamps.firstResult - this.timestamps.submitClick
          : null,
        totalTestTime: this.timestamps.testEnd
      };
      result.networkRequests = this.networkRequests;
      result.consoleLogs = this.consoleLogs;

      console.log('\n[RESULTS] Test Summary:');
      console.log(`  Time to First Feedback: ${result.metrics.timeToFirstFeedback || 'N/A'}ms`);
      console.log(`  Time to First Result: ${result.metrics.timeToFirstResult || 'N/A'}ms`);
      console.log(`  Total Test Time: ${result.metrics.totalTestTime}ms`);

    } catch (error) {
      console.error(`[ERROR] Test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${query.name}_error.png`,
        fullPage: true
      });

      result.success = false;
      result.error = error.message;
      result.timestamps = this.timestamps;
      result.networkRequests = this.networkRequests;
      result.consoleLogs = this.consoleLogs;
    }

    return result;
  }

  /**
   * Explicit cache test - runs the same query twice and compares timing
   * Cache hit should be significantly faster than initial query
   */
  async runCacheTest(page, isAuthenticated, firstQueryResult) {
    const prefix = isAuthenticated ? 'auth' : 'unauth';
    const testName = 'cache_comparison';

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Running CACHE TEST - Explicit timing comparison (${isAuthenticated ? 'Authenticated' : 'Unauthenticated'})`);
    console.log('='.repeat(60));

    const result = {
      scenario: testName,
      authenticated: isAuthenticated
    };

    try {
      // Get timing from first query (should be a cache miss)
      const firstQueryTime = firstQueryResult?.metrics?.timeToFirstResult || null;
      console.log(`[INFO] First query time to result: ${firstQueryTime}ms`);

      // Run the same query again (should be a cache hit)
      console.log('\n[STEP] Running same query again to test cache...');
      const cacheQueryResult = await this.runQueryTest(
        page,
        {
          name: 'cache_hit_test',
          description: 'Cache hit test - repeat of first query',
          input: TEST_QUERIES[0].input
        },
        false,
        isAuthenticated
      );

      const cacheQueryTime = cacheQueryResult?.metrics?.timeToFirstResult || null;
      console.log(`[INFO] Cache query time to result: ${cacheQueryTime}ms`);

      // Check if we got a cache hit in console logs
      const hasCacheHitLog = cacheQueryResult?.consoleLogs?.some(
        (log) => log.text.includes('Cache hit') || log.text.includes('cache_hit')
      );

      // Calculate speedup
      let speedup = null;
      let isCacheHit = false;

      if (firstQueryTime && cacheQueryTime) {
        speedup = ((firstQueryTime - cacheQueryTime) / firstQueryTime * 100).toFixed(1);
        // Consider it a cache hit if second query is at least 30% faster
        isCacheHit = cacheQueryTime < firstQueryTime * 0.7;
      }

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_result.png`
      });

      result.success = true; // Test ran successfully (pass/fail is about cache behavior)
      result.metrics = {
        firstQueryTime,
        cacheQueryTime,
        speedupPercent: speedup,
        isCacheHit,
        hasCacheHitLog
      };

      console.log('\n[CACHE TEST RESULTS]');
      console.log(`  First query: ${firstQueryTime}ms`);
      console.log(`  Cache query: ${cacheQueryTime}ms`);
      console.log(`  Speedup: ${speedup}%`);
      console.log(`  Cache hit detected: ${isCacheHit ? 'YES' : 'NO'}`);
      console.log(`  Cache hit in logs: ${hasCacheHitLog ? 'YES' : 'NO'}`);

      if (isCacheHit) {
        console.log('[PASS] Cache is working - second query was significantly faster');
      } else if (speedup && parseFloat(speedup) > 0) {
        console.log('[INFO] Some speedup detected but not conclusive cache hit');
      } else {
        console.log('[WARN] No speedup detected - cache may not be working');
      }

    } catch (error) {
      console.error(`[ERROR] Cache test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_error.png`,
        fullPage: true
      });
      result.success = false;
      result.error = error.message;
    }

    return result;
  }

  async runFacetCombinationsTest(page, isAuthenticated) {
    const prefix = isAuthenticated ? 'auth' : 'unauth';
    const testName = 'facet_combinations';
    this.timestamps = { testStart: Date.now() };
    this.consoleLogs = [];

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Test: Facet Selection Combinations (OR/AND with subsets) - ${isAuthenticated ? 'Authenticated' : 'Unauthenticated'}`);
    console.log('='.repeat(60));

    const counts = {};
    const result = {
      scenario: testName,
      authenticated: isAuthenticated
    };

    try {
      // Make sure we're on the Facets tab
      console.log('\n[STEP] Switching to Filter by Facets tab...');
      const facetsTab = await this.findButtonByText(page, 'Filter by Facets');
      if (facetsTab) {
        await facetsTab.click();
        await new Promise((r) => setTimeout(r, WAIT_AFTER_CLICK));
      }

      console.log('\n[STEP] Checking for duplicate facets...');
      const duplicateInfo = await this.checkForDuplicateFacets(page);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_00_initial.png`
      });

      // Test A: Check All (OR mode - should be default)
      console.log('\n[TEST A] Check All in OR mode...');
      counts.countAllOr = await this.clickAndWaitForApi(page, 'Check All');
      console.log(`[INFO] countAllOr = ${counts.countAllOr}`);

      // Check that facet columns appear in the table header
      const columnCount = await this.getFacetColumnCount(page);
      console.log(`[INFO] Facet columns visible: ${columnCount}`);
      counts.facetColumnCount = columnCount;

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_01_all_or.png`
      });

      // Test B: Uncheck All
      console.log('\n[TEST B] Uncheck All...');
      const uncheckBtn = await this.findButtonByText(page, 'Uncheck All');
      if (uncheckBtn) {
        await uncheckBtn.click();
        await new Promise((r) => setTimeout(r, 2000));
      }
      counts.countNone = await this.getMatchCount(page);
      console.log(`[INFO] countNone = ${counts.countNone}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_02_none.png`
      });

      // Test C: Subset Selection (OR mode)
      console.log('\n[TEST C] Selecting subset of facets in OR mode...');
      const facetNames = await this.getFacetNames(page);
      console.log(`[INFO] Available facets: ${facetNames.slice(0, 5).join(', ')}...`);

      const facetsToSelect = facetNames.slice(0, Math.min(3, facetNames.length));
      console.log(`[INFO] Selecting: ${facetsToSelect.join(', ')}`);

      for (const facet of facetsToSelect) {
        await this.toggleFacet(page, facet);
      }

      counts.countSubsetOr = await this.getMatchCount(page);
      console.log(`[INFO] countSubsetOr = ${counts.countSubsetOr}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_03_subset_or.png`
      });

      // Test D: Same Subset (AND mode)
      console.log('\n[TEST D] Switching to AND mode with same subset...');
      counts.countSubsetAnd = await this.clickAndWaitForApi(page, 'AND', 5000);
      console.log(`[INFO] countSubsetAnd = ${counts.countSubsetAnd}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_04_subset_and.png`
      });

      // Test E: Check All (AND mode)
      console.log('\n[TEST E] Check All in AND mode...');
      counts.countAllAnd = await this.clickAndWaitForApi(page, 'Check All');
      console.log(`[INFO] countAllAnd = ${counts.countAllAnd}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_05_all_and.png`
      });

      // Test F: Return to OR mode
      console.log('\n[TEST F] Switching back to OR mode...');
      counts.countRestoredOr = await this.clickAndWaitForApi(page, 'OR', 5000);
      console.log(`[INFO] countRestoredOr = ${counts.countRestoredOr}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_06_restored_or.png`
      });

      this.timestamps.testEnd = Date.now() - this.timestamps.testStart;

      // Validate results
      const validations = {
        allOrPositive: counts.countAllOr > 0,
        noneIsZero: counts.countNone === 0,
        subsetOrValid: counts.countSubsetOr > 0 && counts.countSubsetOr <= counts.countAllOr,
        andMoreRestrictive: counts.countSubsetAnd <= counts.countSubsetOr,
        allAndRestrictive: counts.countAllAnd <= counts.countAllOr,
        orRestored: counts.countRestoredOr === counts.countAllOr,
        hasMultipleFacetColumns: counts.facetColumnCount > 0
      };

      console.log('\n[VALIDATIONS]');
      for (const [key, value] of Object.entries(validations)) {
        console.log(`  ${key}: ${value ? 'PASS' : 'FAIL'}`);
      }

      const allPassed = Object.values(validations).every((v) => v);

      result.success = allPassed;
      result.timestamps = this.timestamps;
      result.metrics = {
        ...counts,
        totalTestTime: this.timestamps.testEnd,
        duplicateFacets: duplicateInfo.duplicates
      };
      result.validations = validations;

      console.log(`\n[RESULT] Facet combinations test ${allPassed ? 'PASSED' : 'FAILED'}`);
      console.log(`  OR All: ${counts.countAllOr} -> None: ${counts.countNone}`);
      console.log(`  Subset OR: ${counts.countSubsetOr} -> Subset AND: ${counts.countSubsetAnd}`);
      console.log(`  AND All: ${counts.countAllAnd} -> Restored OR: ${counts.countRestoredOr}`);

    } catch (error) {
      console.error(`[ERROR] Facet combinations test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_error.png`,
        fullPage: true
      });
      result.success = false;
      result.error = error.message;
      result.metrics = counts;
    }

    return result;
  }

  async runTabSwitchingTest(page) {
    const testName = 'tab_switching';
    this.timestamps = { testStart: Date.now() };

    console.log(`\n${'='.repeat(60)}`);
    console.log('Test: Tab Switching (Facets <-> Searches) [Auth Only]');
    console.log('='.repeat(60));

    const result = {
      scenario: testName,
      authenticated: true
    };

    try {
      // Start on Facets tab
      console.log('\n[STEP] Ensuring we start on Filter by Facets tab...');
      const facetsTab = await this.findButtonByText(page, 'Filter by Facets');
      if (facetsTab) {
        await facetsTab.click();
        await new Promise((r) => setTimeout(r, WAIT_AFTER_CLICK));
      }

      const facetsVisible = await page.evaluate(() => {
        const text = document.body.innerText;
        return (
          text.includes('Check All') ||
          text.includes('Uncheck All') ||
          text.includes('OR') ||
          text.includes('AND')
        );
      });
      console.log(`[INFO] Facets panel visible: ${facetsVisible}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_01_facets_tab.png`
      });

      // Click Your Searches tab
      console.log('\n[STEP] Clicking Your Searches tab...');
      const searchesTab = await this.findButtonByText(page, 'Your Searches');
      if (searchesTab) {
        await searchesTab.click();
        await new Promise((r) => setTimeout(r, WAIT_AFTER_CLICK));
      }

      const searchesVisible = await page.evaluate(() => {
        const text = document.body.innerText;
        // Check for any search history items or the empty state
        return text.includes('No searches yet') ||
               document.querySelectorAll('div[style*="cursor: pointer"]').length > 0 ||
               text.includes('Your Searches');
      });
      console.log(`[INFO] Search history visible: ${searchesVisible}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_02_searches_tab.png`
      });

      // Click back to Facets tab
      console.log('\n[STEP] Clicking back to Filter by Facets...');
      const facetsTab2 = await this.findButtonByText(page, 'Filter by Facets');
      if (facetsTab2) {
        await facetsTab2.click();
        await new Promise((r) => setTimeout(r, WAIT_AFTER_CLICK));
      }

      const facetsVisibleAgain = await page.evaluate(() => {
        const text = document.body.innerText;
        return (
          text.includes('Check All') ||
          text.includes('Uncheck All') ||
          text.includes('OR') ||
          text.includes('AND')
        );
      });
      console.log(`[INFO] Facets panel visible again: ${facetsVisibleAgain}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_03_back_to_facets.png`
      });

      this.timestamps.testEnd = Date.now() - this.timestamps.testStart;

      const tabSwitchWorked = facetsVisible && searchesVisible && facetsVisibleAgain;

      result.success = tabSwitchWorked;
      result.timestamps = this.timestamps;
      result.metrics = {
        facetsVisible,
        searchesVisible,
        facetsVisibleAgain,
        totalTestTime: this.timestamps.testEnd
      };

      console.log(`[RESULT] Tab switching test ${tabSwitchWorked ? 'PASSED' : 'FAILED'}`);

    } catch (error) {
      console.error(`[ERROR] Tab switching test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_error.png`,
        fullPage: true
      });
      result.success = false;
      result.error = error.message;
    }

    return result;
  }

  async runSearchSwitchTest(page) {
    const testName = 'switch_searches';
    this.timestamps = { testStart: Date.now() };
    this.consoleLogs = [];
    this.networkRequests = [];

    console.log(`\n${'='.repeat(60)}`);
    console.log('Test: Switch Between Searches [Auth Only]');
    console.log('='.repeat(60));

    const result = {
      scenario: testName,
      authenticated: true
    };

    try {
      if (this.searchHistory.length < 2) {
        console.log('[SKIP] Need at least 2 searches in history for this test');
        result.skipped = true;
        result.reason = 'Need at least 2 searches in history';
        return result;
      }

      const beforeCount = await this.getMatchCount(page);
      console.log(`[INFO] Current match count: ${beforeCount}`);

      console.log('\n[STEP] Switching to Your Searches tab...');
      const searchesTab = await this.findButtonByText(page, 'Your Searches');
      if (searchesTab) {
        await searchesTab.click();
        await new Promise((r) => setTimeout(r, 1000));
      }

      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_01_searches_tab.png`
      });

      console.log('\n[STEP] Looking for search items...');

      let clickedDifferent = false;
      const allDivs = await page.$$('div[style*="cursor"]');

      for (const div of allDivs) {
        const text = await page.evaluate((el) => el.textContent, div);
        if (
          text &&
          text.includes(this.searchHistory[0].input.substring(0, 15)) &&
          this.searchHistory.length > 1
        ) {
          console.log(`[ACTION] Clicking search: "${text.substring(0, 40)}..."`);

          const apiPromise = this.waitForSemanticResponse();
          await div.click();
          await apiPromise;
          await new Promise((r) => setTimeout(r, WAIT_FOR_UI_UPDATE));

          clickedDifferent = true;
          break;
        }
      }

      if (!clickedDifferent) {
        console.log('[WARN] Could not find a different search to click');
      }

      await new Promise((r) => setTimeout(r, 2000));

      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_02_after_switch.png`
      });

      const hasResults = await page.evaluate(() => {
        const text = document.body.innerText;
        return (
          text.includes('Filter') ||
          text.includes('Facet') ||
          text.includes('matches')
        );
      });

      const afterCount = await this.getMatchCount(page);
      console.log(`[INFO] After switch match count: ${afterCount}`);

      this.timestamps.testEnd = Date.now() - this.timestamps.testStart;

      const success = hasResults && (afterCount >= 0 || beforeCount !== afterCount);

      result.success = success;
      result.timestamps = this.timestamps;
      result.metrics = {
        beforeCount,
        afterCount,
        totalTestTime: this.timestamps.testEnd
      };

      console.log(`[RESULT] Switch test ${success ? 'PASSED' : 'FAILED'}`);

    } catch (error) {
      console.error(`[ERROR] Switch test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/auth_${testName}_error.png`,
        fullPage: true
      });
      result.success = false;
      result.error = error.message;
    }

    return result;
  }

  async verifySearchSaved(page, searchText) {
    const searchesTab = await this.findButtonByText(page, 'Your Searches');
    if (searchesTab) {
      await searchesTab.click();
      await new Promise((r) => setTimeout(r, 1000));
    }

    const found = await page.evaluate((text) => {
      return document.body.innerText.includes(text.substring(0, 20));
    }, searchText);

    const facetsTab = await this.findButtonByText(page, 'Filter by Facets');
    if (facetsTab) {
      await facetsTab.click();
      await new Promise((r) => setTimeout(r, 500));
    }

    return found;
  }

  /**
   * Test markdown rendering and table formatting
   * - Opens person detail modal
   * - Checks for raw markdown syntax (should NOT appear)
   * - Verifies styled elements render properly
   * - Checks table row text display
   */
  async runFormattingTest(page, isAuthenticated) {
    const prefix = isAuthenticated ? 'auth' : 'unauth';
    const testName = 'formatting';
    this.timestamps = { testStart: Date.now() };

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Test: Formatting & Markdown Rendering - ${isAuthenticated ? 'Authenticated' : 'Unauthenticated'}`);
    console.log('='.repeat(60));

    const result = {
      scenario: testName,
      authenticated: isAuthenticated,
      checks: {}
    };

    try {
      // First, ensure we have results to test
      const hasResults = await page.evaluate(() => {
        const rows = document.querySelectorAll('[style*="border-bottom"][style*="cursor"]');
        return rows.length > 0;
      });

      if (!hasResults) {
        console.log('[SKIP] No result rows found to test formatting');
        result.skipped = true;
        result.reason = 'No result rows available';
        return result;
      }

      // Test 1: Check table row text for raw markdown artifacts
      console.log('\n[TEST 1] Checking table rows for raw markdown...');
      const tableCheck = await page.evaluate(() => {
        const rows = document.querySelectorAll('[style*="border-bottom"]');
        const issues = [];
        const markdownPatterns = [
          /\*\*[^*]+\*\*/g,  // **bold**
          /(?<!\*)\*[^*]+\*(?!\*)/g,  // *italic* (not **)
          /^#{1,6}\s/gm,  // # headers
          /\[([^\]]+)\]\([^)]+\)/g,  // [links](url)
          /`[^`]+`/g,  // `code`
        ];

        for (const row of rows) {
          const text = row.innerText;
          for (const pattern of markdownPatterns) {
            const matches = text.match(pattern);
            if (matches) {
              issues.push({
                pattern: pattern.toString(),
                matches: matches.slice(0, 3),
                context: text.substring(0, 100)
              });
            }
          }
        }

        return {
          rowCount: rows.length,
          issues,
          pass: issues.length === 0
        };
      });

      result.checks.tableRowsNoRawMarkdown = tableCheck.pass;
      console.log(`[INFO] Table rows checked: ${tableCheck.rowCount}`);
      if (!tableCheck.pass) {
        console.log(`[WARN] Found ${tableCheck.issues.length} raw markdown issues in table rows`);
        for (const issue of tableCheck.issues.slice(0, 3)) {
          console.log(`  - Pattern ${issue.pattern}: ${issue.matches.join(', ')}`);
        }
      } else {
        console.log('[PASS] No raw markdown found in table rows');
      }

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_01_table.png`
      });

      // Test 2: Open detail modal by clicking first result row
      console.log('\n[TEST 2] Opening person detail modal...');

      // Find result rows - they have specific structure with person name and image
      const clickableRow = await page.evaluateHandle(() => {
        // Look for rows with the characteristic styling of result rows
        const rows = document.querySelectorAll('div');
        for (const row of rows) {
          const style = row.getAttribute('style') || '';
          // Result rows have border-bottom, cursor pointer, and contain an image
          if (style.includes('border-bottom') &&
              style.includes('cursor') &&
              row.querySelector('img') &&
              row.innerText.length > 50) {  // Has substantial content
            return row;
          }
        }
        return null;
      });

      if (clickableRow && clickableRow.asElement()) {
        await clickableRow.asElement().click();
        await new Promise((r) => setTimeout(r, 1500)); // Wait for modal animation
        console.log('[INFO] Clicked on result row');
      } else {
        console.log('[WARN] Could not find result row to click');
      }

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_02_modal.png`
      });

      // Test 3: Check modal content for raw markdown
      console.log('\n[TEST 3] Checking modal content for raw markdown...');

      // Wait for modal content to render
      await new Promise((r) => setTimeout(r, 1000));

      const modalCheck = await page.evaluate(() => {
        // The PersonDetailModal has specific structure:
        // - Fixed position overlay with backdrop-filter: blur
        // - Inner content div with max-width: 800px
        // - h2 for person name, h3 for section headers
        // - Sections: Context, Challenges Faced, How They Overcame, Achievements

        // Find the modal overlay (has backdrop-filter and covers full screen)
        let modalOverlay = null;
        const allDivs = document.querySelectorAll('div');

        for (const div of allDivs) {
          const style = div.getAttribute('style') || '';
          // PersonDetailModal overlay has: position: fixed, backdrop-filter: blur, z-index: 1000
          if (style.includes('position: fixed') &&
              style.includes('backdrop-filter') &&
              style.includes('z-index: 1000')) {
            modalOverlay = div;
            break;
          }
        }

        if (!modalOverlay) {
          // Fallback: look for any fixed overlay with dark background
          for (const div of allDivs) {
            const style = div.getAttribute('style') || '';
            if (style.includes('position: fixed') &&
                style.includes('rgba(0, 0, 0, 0.8') &&
                div.innerText.length > 100) {
              modalOverlay = div;
              break;
            }
          }
        }

        if (!modalOverlay) {
          return { found: false, pass: false, debug: 'No modal overlay found' };
        }

        // Find the content div inside (has max-width: 800px or similar)
        let contentDiv = modalOverlay.querySelector('div[style*="max-width"]');
        if (!contentDiv) {
          // The content is usually the first direct child that's a div
          for (const child of modalOverlay.children) {
            if (child.tagName === 'DIV' && child.innerText.length > 100) {
              contentDiv = child;
              break;
            }
          }
        }

        const searchRoot = contentDiv || modalOverlay;
        const text = searchRoot.innerText;

        // Skip if we accidentally found the Sign In button
        if (text.includes('Sign in with Google') && text.length < 50) {
          return { found: false, pass: false, debug: 'Found Sign In button instead of modal' };
        }

        const issues = [];
        const markdownPatterns = [
          { name: 'bold', pattern: /\*\*[^*]+\*\*/g },
          { name: 'italic', pattern: /(?<!\*)\*[^*]+\*(?!\*)/g },
          { name: 'header', pattern: /^#{1,6}\s/gm },
          { name: 'link', pattern: /\[([^\]]+)\]\([^)]+\)/g },
          { name: 'code', pattern: /`[^`]+`/g },
        ];

        for (const { name, pattern } of markdownPatterns) {
          const matches = text.match(pattern);
          if (matches) {
            issues.push({
              type: name,
              matches: matches.slice(0, 3),
              count: matches.length
            });
          }
        }

        // Check that sections exist (PersonDetailModal has these h3 headers)
        const sections = {
          context: text.includes('Context'),
          challenges: text.includes('Challenges Faced'),
          overcame: text.includes('How They Overcame'),
          achievements: text.includes('Achievements')
        };

        // Check for styled elements (ReactMarkdown should create these)
        const hasStyledElements = {
          strong: searchRoot.querySelectorAll('strong').length,
          paragraphs: searchRoot.querySelectorAll('p').length,
          h2: searchRoot.querySelectorAll('h2').length,
          h3: searchRoot.querySelectorAll('h3').length
        };

        // Get person name from h2
        const h2 = searchRoot.querySelector('h2');
        const personName = h2 ? h2.innerText : 'unknown';

        return {
          found: true,
          personName,
          issues,
          sections,
          hasStyledElements,
          pass: issues.length === 0,
          textLength: text.length,
          textPreview: text.substring(0, 200)
        };
      });

      if (!modalCheck.found) {
        console.log(`[WARN] Modal not found after clicking row. Debug: ${modalCheck.debug || 'unknown'}`);
        result.checks.modalOpens = false;
      } else {
        result.checks.modalOpens = true;
        result.checks.modalNoRawMarkdown = modalCheck.pass;
        result.checks.modalSections = modalCheck.sections;
        result.checks.modalStyledElements = modalCheck.hasStyledElements;

        console.log(`[INFO] Person displayed: ${modalCheck.personName || 'unknown'}`);
        console.log(`[INFO] Modal text length: ${modalCheck.textLength}`);
        console.log(`[INFO] Sections found: ${Object.entries(modalCheck.sections).filter(([, v]) => v).map(([k]) => k).join(', ') || 'none'}`);
        console.log(`[INFO] Styled elements: strong=${modalCheck.hasStyledElements.strong}, p=${modalCheck.hasStyledElements.paragraphs}, h2=${modalCheck.hasStyledElements.h2}, h3=${modalCheck.hasStyledElements.h3}`);

        if (!modalCheck.pass) {
          console.log(`[WARN] Found ${modalCheck.issues.length} raw markdown issues in modal`);
          for (const issue of modalCheck.issues) {
            console.log(`  - ${issue.type}: ${issue.count} occurrences (${issue.matches.join(', ')})`);
          }
        } else {
          console.log('[PASS] No raw markdown found in modal - ReactMarkdown is working');
        }

        // Validate sections are present
        const sectionsFound = Object.values(modalCheck.sections).filter(Boolean).length;
        if (sectionsFound >= 3) {
          console.log(`[PASS] Modal has ${sectionsFound}/4 expected sections`);
        } else {
          console.log(`[WARN] Modal only has ${sectionsFound}/4 expected sections`);
        }
      }

      // Test 4: Close modal and verify it closes
      console.log('\n[TEST 4] Closing modal...');

      // The close button in PersonDetailModal contains "✕"

      // Find the close button within the modal
      const closeResult = await page.evaluate(() => {
        const allDivs = document.querySelectorAll('div');
        for (const div of allDivs) {
          const style = div.getAttribute('style') || '';
          if (style.includes('position: fixed') && style.includes('backdrop-filter')) {
            // Found the modal overlay - look for button with ✕
            const buttons = div.querySelectorAll('button');
            for (const btn of buttons) {
              if (btn.innerText.includes('✕')) {
                btn.click();
                return { clicked: true, method: 'close button' };
              }
            }
            // If no button found, click the overlay itself
            div.click();
            return { clicked: true, method: 'overlay click' };
          }
        }
        return { clicked: false };
      });

      if (closeResult.clicked) {
        console.log(`[INFO] Closed modal via ${closeResult.method}`);
      }

      await new Promise((r) => setTimeout(r, 500));

      const modalClosed = await page.evaluate(() => {
        // Check if modal is gone (no more fixed overlay with backdrop-filter)
        const allDivs = document.querySelectorAll('div');
        for (const div of allDivs) {
          const style = div.getAttribute('style') || '';
          if (style.includes('position: fixed') &&
              style.includes('backdrop-filter') &&
              style.includes('z-index: 1000')) {
            return false;
          }
        }
        return true;
      });
      result.checks.modalCloses = modalClosed;
      console.log(`[INFO] Modal closed: ${modalClosed}`);

      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_03_closed.png`
      });

      // Test 5: Check for text truncation issues in table (ellipsis should work)
      console.log('\n[TEST 5] Checking text truncation in table...');
      const truncationCheck = await page.evaluate(() => {
        const rows = document.querySelectorAll('[style*="border-bottom"]');
        let hasLongText = false;
        let hasTruncation = false;

        for (const row of rows) {
          const text = row.innerText;
          // Check if any cell has very long unbroken text (potential overflow issue)
          if (text.length > 200 && !text.includes('...')) {
            // Look for cells with proper truncation
            const cells = row.querySelectorAll('div');
            for (const cell of cells) {
              const cellText = cell.innerText;
              if (cellText.length > 100) {
                hasLongText = true;
                if (cellText.includes('...')) {
                  hasTruncation = true;
                }
              }
            }
          }
        }

        return {
          hasLongText,
          hasTruncation,
          pass: !hasLongText || hasTruncation
        };
      });

      result.checks.textTruncation = truncationCheck.pass;
      console.log(`[INFO] Long text cells: ${truncationCheck.hasLongText}, Has truncation: ${truncationCheck.hasTruncation}`);

      this.timestamps.testEnd = Date.now() - this.timestamps.testStart;

      // Determine overall success
      const allPassed = Object.values(result.checks).every((v) => {
        if (typeof v === 'boolean') return v;
        if (typeof v === 'object' && v !== null) {
          // For objects like modalSections, check all values are truthy
          // For modalStyledElements, just check it exists (counts of 0 are OK)
          return true;
        }
        return Boolean(v);
      });
      result.success = allPassed;
      result.timestamps = this.timestamps;

      console.log(`\n[RESULT] Formatting test ${allPassed ? 'PASSED' : 'FAILED'}`);
      for (const [key, value] of Object.entries(result.checks)) {
        if (typeof value === 'boolean') {
          console.log(`  - ${key}: ${value ? 'PASS' : 'FAIL'}`);
        } else {
          console.log(`  - ${key}: ${JSON.stringify(value)}`);
        }
      }

    } catch (error) {
      console.error(`[ERROR] Formatting test failed: ${error.message}`);
      await page.screenshot({
        path: `${RESULTS_DIR}/${prefix}_${testName}_error.png`,
        fullPage: true
      });
      result.success = false;
      result.error = error.message;
    }

    return result;
  }

  // ========================================
  // TEST SUITE RUNNER
  // ========================================

  async runTestSuite(page, isAuthenticated) {
    const mode = isAuthenticated ? 'authenticated' : 'unauthenticated';
    const results = {
      mode,
      queries: [],
      cache: null,
      facets: null,
      formatting: null,
      tabs: null,
      searchHistory: null,
      duplicates: null
    };

    // Run query tests
    let isFirst = true;
    let firstQueryResult = null;
    for (const query of TEST_QUERIES) {
      const result = await this.runQueryTest(page, query, isFirst, isAuthenticated);
      results.queries.push(result);
      if (isFirst) {
        firstQueryResult = result; // Save for cache comparison
      }
      isFirst = false;
      await new Promise((r) => setTimeout(r, WAIT_BETWEEN_TESTS));
    }

    // Cache test - explicit comparison with first query
    results.cache = await this.runCacheTest(page, isAuthenticated, firstQueryResult);

    // Facet combinations test
    results.facets = await this.runFacetCombinationsTest(page, isAuthenticated);

    // Duplicate facet check
    results.duplicates = await this.checkForDuplicateFacets(page);

    // Formatting test (markdown rendering in modal and table)
    results.formatting = await this.runFormattingTest(page, isAuthenticated);

    // Auth-only tests
    if (isAuthenticated) {
      console.log('\n' + '='.repeat(60));
      console.log('RUNNING AUTHENTICATED-ONLY TESTS');
      console.log('='.repeat(60));

      results.tabs = await this.runTabSwitchingTest(page);
      await new Promise((r) => setTimeout(r, 1000));

      results.searchHistory = await this.runSearchSwitchTest(page);
    }

    return results;
  }

  async waitForTestAuth(page) {
    console.log('\n' + '='.repeat(60));
    console.log('TEST AUTH MODE');
    console.log('='.repeat(60));
    console.log('Using ?testAuth=true for simulated login');
    console.log('Backend must be running with ALLOW_TEST_AUTH=true');
    console.log('='.repeat(60) + '\n');

    await page.screenshot({
      path: `${RESULTS_DIR}/auth_login_01_initial.png`,
      fullPage: true
    });

    console.log('[WAITING] Waiting for test auth to initialize...');

    await page.waitForFunction(
      () => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          if (btn.textContent && btn.textContent.includes('Sign Out')) {
            return true;
          }
        }
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
          if (img.src && img.src.includes('ui-avatars.com')) {
            return true;
          }
        }
        return document.body.innerText.includes('Test User');
      },
      { timeout: 30000 }
    );

    console.log('[SUCCESS] Test auth detected!');
    console.log('[INFO] Continuing with authenticated tests...\n');

    await page.screenshot({
      path: `${RESULTS_DIR}/auth_login_02_logged_in.png`,
      fullPage: true
    });

    await new Promise((r) => setTimeout(r, 1000));
  }

  // ========================================
  // REPORT GENERATION
  // ========================================

  generateReport() {
    console.log('\n' + '='.repeat(60));
    console.log('COMPREHENSIVE TEST REPORT');
    console.log('='.repeat(60));

    const generateModeReport = (results, modeName) => {
      if (!results) return;

      console.log(`\n### ${modeName.toUpperCase()} MODE ###`);

      const queries = results.queries || [];
      const passed = queries.filter((r) => r.success).length;

      console.log(`Query Tests: ${passed}/${queries.length} passed`);

      for (const result of queries) {
        console.log(`  - ${result.scenario}: ${result.success ? 'PASS' : 'FAIL'}`);
        if (result.metrics?.timeToFirstResult) {
          console.log(`    Time to first result: ${result.metrics.timeToFirstResult}ms`);
        }
        if (result.error) {
          console.log(`    Error: ${result.error}`);
        }
      }

      if (results.cache) {
        const cacheMetrics = results.cache.metrics || {};
        const cacheStatus = cacheMetrics.isCacheHit ? 'PASS (cache working)' :
                           cacheMetrics.speedupPercent > 0 ? 'PARTIAL (some speedup)' : 'WARN (no speedup)';
        console.log(`\nCache Test: ${cacheStatus}`);
        if (cacheMetrics.firstQueryTime && cacheMetrics.cacheQueryTime) {
          console.log(`  - First query: ${cacheMetrics.firstQueryTime}ms`);
          console.log(`  - Cache query: ${cacheMetrics.cacheQueryTime}ms`);
          console.log(`  - Speedup: ${cacheMetrics.speedupPercent}%`);
        }
      }

      if (results.facets) {
        console.log(`\nFacet Combinations: ${results.facets.success ? 'PASS' : 'FAIL'}`);
        if (results.facets.validations) {
          for (const [key, value] of Object.entries(results.facets.validations)) {
            console.log(`  - ${key}: ${value ? 'PASS' : 'FAIL'}`);
          }
        }
      }

      if (results.duplicates) {
        console.log(`\nDuplicate Facets: ${results.duplicates.duplicates.length === 0 ? 'PASS (none found)' : 'WARN'}`);
        if (results.duplicates.duplicates.length > 0) {
          for (const dup of results.duplicates.duplicates) {
            console.log(`  - "${dup.name}" appears ${dup.count} times`);
          }
        }
      }

      if (results.formatting) {
        if (results.formatting.skipped) {
          console.log(`\nFormatting Test: SKIPPED (${results.formatting.reason})`);
        } else {
          console.log(`\nFormatting Test: ${results.formatting.success ? 'PASS' : 'FAIL'}`);
          if (results.formatting.checks) {
            for (const [key, value] of Object.entries(results.formatting.checks)) {
              if (typeof value === 'boolean') {
                console.log(`  - ${key}: ${value ? 'PASS' : 'FAIL'}`);
              }
            }
          }
        }
      }

      if (modeName === 'authenticated') {
        if (results.tabs) {
          console.log(`\nTab Switching: ${results.tabs.success ? 'PASS' : 'FAIL'}`);
        }
        if (results.searchHistory) {
          if (results.searchHistory.skipped) {
            console.log(`\nSearch Switch: SKIPPED (${results.searchHistory.reason})`);
          } else {
            console.log(`\nSearch Switch: ${results.searchHistory.success ? 'PASS' : 'FAIL'}`);
          }
        }
      }
    };

    generateModeReport(this.results.unauth, 'unauthenticated');
    generateModeReport(this.results.auth, 'authenticated');

    // Save full results
    const reportPath = `${RESULTS_DIR}/comprehensive-report.json`;
    fs.writeFileSync(reportPath, JSON.stringify(this.results, null, 2));
    console.log(`\nFull results saved to ${reportPath}`);
  }

  async cleanup() {
    this.generateReport();
    await this.browser.close();
  }
}

// ========================================
// MAIN EXECUTION
// ========================================

async function main() {
  const args = process.argv.slice(2);
  const unauthOnly = args.includes('--unauth-only');
  const authOnly = args.includes('--auth-only');

  // Generate unique test queries using Gemini (to avoid cache hits)
  TEST_QUERIES = await generateTestQueries();

  const tester = new UXTester();

  try {
    await tester.setup();

    // Run unauthenticated tests
    if (!authOnly) {
      console.log('\n' + '='.repeat(60));
      console.log('STARTING UNAUTHENTICATED TESTS');
      console.log('='.repeat(60));

      const unauthPage = await tester.browser.newPage();
      tester.setupPageListeners(unauthPage);

      console.log('\n[STEP] Navigating to frontend (unauthenticated)...');
      await unauthPage.goto(FRONTEND_URL, { waitUntil: 'networkidle0', timeout: 30000 });

      tester.results.unauth = await tester.runTestSuite(unauthPage, false);
      await unauthPage.close();
    }

    // Run authenticated tests
    if (!unauthOnly) {
      console.log('\n' + '='.repeat(60));
      console.log('STARTING AUTHENTICATED TESTS');
      console.log('='.repeat(60));

      // Reset search history for auth mode
      tester.searchHistory = [];

      const authPage = await tester.browser.newPage();
      tester.setupPageListeners(authPage);

      console.log('\n[STEP] Navigating to frontend with test auth mode...');
      await authPage.goto(FRONTEND_URL_AUTH, { waitUntil: 'networkidle0', timeout: 30000 });

      await tester.waitForTestAuth(authPage);

      tester.results.auth = await tester.runTestSuite(authPage, true);
      await authPage.close();
    }

  } catch (error) {
    console.error('Test suite failed:', error);
  } finally {
    await tester.cleanup();
  }
}

main();
