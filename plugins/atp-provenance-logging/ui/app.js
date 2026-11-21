/* ATP Mission Control — precompiled (public plugin build, synced from Prove). */
(function () {
  'use strict';

  if (typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
    document.getElementById('fallback').setAttribute('data-reason', 'react-missing');
    return;
  }
  var useState = React.useState,
    useEffect = React.useEffect,
    useMemo = React.useMemo,
    useCallback = React.useCallback,
    useRef = React.useRef;

  // ── Inline SVG icon shim (replaces lucide-react in the standalone build) ──
  // Keeps the standalone file fully offline-capable: no icon CDN required.
  const _icon = paths => ({
    size = 16,
    className = '',
    ...rest
  }) => React.createElement('svg', {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    className,
    ...rest
  }, paths.map((d, i) => typeof d === 'string' ? React.createElement('path', {
    key: i,
    d
  }) : React.createElement(d.t, {
    key: i,
    ...d.p
  })));
  const C = p => ({
    t: 'circle',
    p
  });
  const L = p => ({
    t: 'line',
    p
  });
  const R = p => ({
    t: 'rect',
    p
  });
  const PL = p => ({
    t: 'polyline',
    p
  });
  const Play = _icon([{
    t: 'polygon',
    p: {
      points: '5 3 19 12 5 21 5 3'
    }
  }]);
  const Pause = _icon([R({
    x: 6,
    y: 4,
    width: 4,
    height: 16
  }), R({
    x: 14,
    y: 4,
    width: 4,
    height: 16
  })]);
  const RotateCcw = _icon(['M3 12a9 9 0 1 0 3-6.7L3 8', PL({
    points: '3 3 3 8 8 8'
  })]);
  const GitBranch = _icon([L({
    x1: 6,
    y1: 3,
    x2: 6,
    y2: 15
  }), C({
    cx: 18,
    cy: 6,
    r: 3
  }), C({
    cx: 6,
    cy: 18,
    r: 3
  }), 'M18 9a9 9 0 0 1-9 9']);
  const FileText = _icon(['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', PL({
    points: '14 2 14 8 20 8'
  }), L({
    x1: 8,
    y1: 13,
    x2: 16,
    y2: 13
  }), L({
    x1: 8,
    y1: 17,
    x2: 14,
    y2: 17
  })]);
  const Terminal = _icon([PL({
    points: '4 17 10 11 4 5'
  }), L({
    x1: 12,
    y1: 19,
    x2: 20,
    y2: 19
  })]);
  const Database = _icon([{
    t: 'ellipse',
    p: {
      cx: 12,
      cy: 5,
      rx: 9,
      ry: 3
    }
  }, 'M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5', 'M3 12c0 1.7 4 3 9 3s9-1.3 9-3']);
  const CheckCircle = _icon(['M22 11.1V12a10 10 0 1 1-5.9-9.1', PL({
    points: '22 4 12 14.01 9 11.01'
  })]);
  const Clock = _icon([C({
    cx: 12,
    cy: 12,
    r: 10
  }), PL({
    points: '12 6 12 12 16 14'
  })]);
  const Zap = _icon([{
    t: 'polygon',
    p: {
      points: '13 2 3 14 12 14 11 22 21 10 12 10 13 2'
    }
  }]);
  const Radio = _icon([C({
    cx: 12,
    cy: 12,
    r: 2
  }), 'M7.8 16.2a6 6 0 0 1 0-8.4', 'M16.2 7.8a6 6 0 0 1 0 8.4', 'M4.9 19.1a10 10 0 0 1 0-14.2', 'M19.1 4.9a10 10 0 0 1 0 14.2']);
  const Shield = _icon(['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z']);
  const Link2 = _icon(['M9 17H7A5 5 0 0 1 7 7h2', 'M15 7h2a5 5 0 0 1 0 10h-2', L({
    x1: 8,
    y1: 12,
    x2: 16,
    y2: 12
  })]);
  const Upload = _icon(['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', PL({
    points: '17 8 12 3 7 8'
  }), L({
    x1: 12,
    y1: 3,
    x2: 12,
    y2: 15
  })]);
  const AlertTriangle = _icon(['M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z', L({
    x1: 12,
    y1: 9,
    x2: 12,
    y2: 13
  }), L({
    x1: 12,
    y1: 17,
    x2: 12.01,
    y2: 17
  })]);
  const ArrowLeft = _icon([L({
    x1: 19,
    y1: 12,
    x2: 5,
    y2: 12
  }), PL({
    points: '12 19 5 12 12 5'
  })]);
  const Server = _icon([R({
    x: 2,
    y: 2,
    width: 20,
    height: 8,
    rx: 2
  }), R({
    x: 2,
    y: 14,
    width: 20,
    height: 8,
    rx: 2
  }), L({
    x1: 6,
    y1: 6,
    x2: 6.01,
    y2: 6
  }), L({
    x1: 6,
    y1: 18,
    x2: 6.01,
    y2: 18
  })]);
  const Globe = _icon([C({
    cx: 12,
    cy: 12,
    r: 10
  }), L({
    x1: 2,
    y1: 12,
    x2: 22,
    y2: 12
  }), 'M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z']);
  const Folder = _icon(['M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z']);
  const User = _icon(['M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2', C({
    cx: 12,
    cy: 7,
    r: 4
  })]);
  const AGENT_PROFILES = ['Claude-Code', 'Codex', 'Subagent'];
  const MODES = ['Build', 'Review', 'Organize', 'Capture', 'Synthesize', 'Commit'];
  const ACTION_TYPES = ['Summarize', 'Scaffold', 'Execute', 'Reflect'];
  const PRIORITIES = ['Critical', 'High', 'Normal', 'Low'];
  // Served over HTTP(S) by Prove (local or hosted): talk to the same origin.
  // Opened from disk (prove-offline.html): fall back to the local service.
  const DEFAULT_PROVENANCE_URL = /^https?:$/.test(window.location.protocol) ? window.location.origin : 'http://127.0.0.1:8787';
  // IDs come from the browser's CSPRNG (crypto.randomUUID, or getRandomValues
  // as a fallback), never Math.random.
  const generateUUID = () => {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    const bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = bytes[6] & 0x0f | 0x40;
    bytes[8] = bytes[8] & 0x3f | 0x80;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  };

  // ═══════════════════════════════════════════════════════════
  // PHASE STYLING
  // ═══════════════════════════════════════════════════════════

  const phaseIcons = {
    atp_prompt: GitBranch,
    read_file: FileText,
    write_file: FileText,
    execute_command: Terminal,
    tool_call: Database,
    atp_response: CheckCircle,
    mint: Link2,
    health: Radio,
    embed: Shield
  };
  const phaseColors = {
    atp_prompt: {
      bg: 'bg-violet-500',
      border: 'border-violet-400',
      glow: 'shadow-violet-500/50',
      text: 'text-violet-400'
    },
    read_file: {
      bg: 'bg-sky-500',
      border: 'border-sky-400',
      glow: 'shadow-sky-500/50',
      text: 'text-sky-400'
    },
    write_file: {
      bg: 'bg-emerald-500',
      border: 'border-emerald-400',
      glow: 'shadow-emerald-500/50',
      text: 'text-emerald-400'
    },
    execute_command: {
      bg: 'bg-amber-500',
      border: 'border-amber-400',
      glow: 'shadow-amber-500/50',
      text: 'text-amber-400'
    },
    tool_call: {
      bg: 'bg-rose-500',
      border: 'border-rose-400',
      glow: 'shadow-rose-500/50',
      text: 'text-rose-400'
    },
    atp_response: {
      bg: 'bg-teal-500',
      border: 'border-teal-400',
      glow: 'shadow-teal-500/50',
      text: 'text-teal-400'
    },
    mint: {
      bg: 'bg-indigo-500',
      border: 'border-indigo-400',
      glow: 'shadow-indigo-500/50',
      text: 'text-indigo-400'
    },
    health: {
      bg: 'bg-cyan-500',
      border: 'border-cyan-400',
      glow: 'shadow-cyan-500/50',
      text: 'text-cyan-400'
    },
    embed: {
      bg: 'bg-fuchsia-500',
      border: 'border-fuchsia-400',
      glow: 'shadow-fuchsia-500/50',
      text: 'text-fuchsia-400'
    }
  };
  const simulatedActions = [{
    phase: 'read_file',
    input: {
      path: 'src/config.ts'
    },
    output: {
      summary: 'Configuration loaded'
    },
    tags: ['read']
  }, {
    phase: 'tool_call',
    input: {
      tool: 'supabase',
      action: 'query'
    },
    output: {
      summary: 'Fetched 42 records'
    },
    tags: ['tool', 'database']
  }, {
    phase: 'execute_command',
    input: {
      cmd: 'npm test'
    },
    output: {
      summary: '23 tests passed'
    },
    tags: ['execute', 'test']
  }, {
    phase: 'write_file',
    input: {
      path: 'dist/bundle.js'
    },
    output: {
      summary: 'Bundle written (245kb)'
    },
    tags: ['write']
  }, {
    phase: 'tool_call',
    input: {
      tool: 'mcp_github',
      action: 'create_pr'
    },
    output: {
      summary: 'PR #127 created'
    },
    tags: ['tool', 'github']
  }];

  // ═══════════════════════════════════════════════════════════
  // PROVENANCE CHAIN — 8-Step Model (atp-provenance-logging)
  // ═══════════════════════════════════════════════════════════

  const PROVENANCE_STEPS = [{
    id: 'mint_parent',
    step: 1,
    label: 'Mint Parent ProvID',
    description: 'POST /mint → parent prov_id minted',
    phase: 'atp_prompt',
    failAction: 'HALT — no actions valid without parent prov_id'
  }, {
    id: 'embed_header',
    step: 2,
    label: 'Embed ProvID in Header',
    description: 'prov_id in [[Special Instructions]]',
    phase: 'atp_prompt',
    failAction: 'HALT — header untraceable'
  }, {
    id: 'log_prompt',
    step: 3,
    label: 'Log ATP Prompt Root',
    description: 'parent_prov_id=null, phase="atp_prompt"',
    phase: 'atp_prompt',
    failAction: 'HALT — outputs invalid'
  }, {
    id: 'log_actions',
    step: 4,
    label: 'Log Child Actions',
    description: 'Every tool call/read/write/execute → child prov_id',
    phase: 'execution',
    failAction: 'HALT — outputs invalid without child provenance'
  }, {
    id: 'log_errors',
    step: 5,
    label: 'Error Lineage Preserved',
    description: 'Errors logged, parent linkage maintained',
    phase: 'execution',
    failAction: 'WARN — broken lineage on error path'
  }, {
    id: 'log_response',
    step: 6,
    label: 'Log ATP Response',
    description: 'Final entry: phase="atp_response"',
    phase: 'atp_response',
    failAction: 'HALT — response invalid'
  }, {
    id: 'schema_valid',
    step: 7,
    label: 'Payload Schema Match',
    description: 'All required fields present in every log',
    phase: 'validation',
    failAction: 'WARN — schema drift'
  }, {
    id: 'chain_complete',
    step: 8,
    label: 'Chain Integrity',
    description: '1 parent, no orphans, no gaps',
    phase: 'validation',
    failAction: 'FAIL — triggers human review'
  }];
  const REQUIRED_LOG_FIELDS = ['prov_id', 'parent_prov_id', 'actor', 'phase', 'status', 'tags'];
  const validateLogSchema = entry => {
    const missing = REQUIRED_LOG_FIELDS.filter(f => !(f in entry));
    return {
      valid: missing.length === 0,
      missing
    };
  };
  const validateChainIntegrity = (logs, parentProvId) => {
    const roots = logs.filter(l => l.parent_prov_id === null && l.phase === 'atp_prompt');
    const orphans = logs.filter(l => l.parent_prov_id !== null && l.parent_prov_id !== parentProvId && !logs.some(p => p.prov_id === l.parent_prov_id));
    const hasResponse = logs.some(l => l.phase === 'atp_response');
    return {
      exactlyOneParent: roots.length === 1,
      noOrphans: orphans.length === 0,
      orphanCount: orphans.length,
      hasResponse,
      valid: roots.length === 1 && orphans.length === 0
    };
  };

  // ═══════════════════════════════════════════════════════════
  // JSON IMPORT — Format Detection + Normalization
  // Formats: agent_logs array | Claude session snapshot | wrapped {logs:[]}
  // ═══════════════════════════════════════════════════════════

  function detectImportFormat(data) {
    // Artemis MCP chain: entries with `kind` (atp_prompt/agent_action) from read_provenance_chain
    if (Array.isArray(data) && data.length > 0 && data[0].prov_id && data[0].kind) return 'artemis_chain';
    if (Array.isArray(data) && data.length > 0 && data[0].prov_id) return 'agent_logs';
    if (data && Array.isArray(data.logs) && data.logs.length > 0 && data.logs[0].prov_id) return 'agent_logs_wrapped';
    if (data && (data.sessionId || data.cliSessionId) && (data.permissionMode || data.model)) return 'claude_session';
    if (Array.isArray(data)) return 'unknown_array';
    return 'unknown';
  }

  // Parse a Claude local-agent session snapshot into a governance profile
  function parseSessionSnapshot(data) {
    const mcpServers = (data.remoteMcpServersConfig || []).map(s => ({
      name: s.name || 'unknown',
      uuid: s.uuid,
      toolCount: Array.isArray(s.tools) ? s.tools.length : 0
    }));
    const enabledToolCount = data.enabledMcpTools ? Object.keys(data.enabledMcpTools).length : 0;
    return {
      identity: {
        sessionId: data.sessionId || '—',
        cliSessionId: data.cliSessionId || '—',
        processName: data.processName || data.vmProcessName || '—',
        title: data.title || 'Untitled session',
        account: data.accountName || '—',
        model: data.model || '—'
      },
      governance: {
        permissionMode: data.permissionMode || 'unknown',
        hostLoopMode: !!data.hostLoopMode,
        execPolicies: data.orgCliExecPolicies?.policies ? Object.keys(data.orgCliExecPolicies.policies).length : 0,
        memoryEnabled: !!data.memoryEnabled,
        skillsEnabled: !!data.skillsEnabled,
        pluginsEnabled: !!data.pluginsEnabled
      },
      scope: {
        cwd: data.cwd || '—',
        selectedFolders: data.userSelectedFolders || [],
        egressDomains: data.egressAllowedDomains || [],
        webFetchUrls: data.webFetchAllowedUrls || []
      },
      toolSurface: {
        mcpServers,
        enabledToolCount,
        slashCommands: (data.slashCommands || []).length
      },
      timeline: {
        createdAt: data.createdAt || null,
        lastActivityAt: data.lastActivityAt || null,
        durationHrs: data.createdAt && data.lastActivityAt ? ((data.lastActivityAt - data.createdAt) / 3600000).toFixed(1) : null
      },
      initialMessage: (data.initialMessage || '').slice(0, 400)
    };
  }

  // Normalize imported agent_logs entries to our display shape
  function normalizeLogs(rawLogs) {
    return rawLogs.map(l => ({
      prov_id: l.prov_id || generateUUID(),
      parent_prov_id: l.parent_prov_id !== undefined ? l.parent_prov_id : null,
      actor: l.actor || 'unknown',
      model: l.model || null,
      phase: l.phase || 'tool_call',
      input: l.input || null,
      output: l.output || null,
      status: l.status || 'ok',
      error: l.error || null,
      latency_ms: l.latency_ms != null ? l.latency_ms : null,
      tags: Array.isArray(l.tags) ? l.tags : [],
      timestamp: l.timestamp || null,
      body_sha256: l.body_sha256 || null,
      manifest_binding_id: l.manifest_binding_id || null,
      refs: l.refs || null,
      prev_action_hash: l.prev_action_hash || null,
      semantic_fingerprint: l.semantic_fingerprint || null,
      sequence_no: l.sequence_no != null ? l.sequence_no : null
    }));
  }

  // Normalize Artemis MCP chain entries (read_provenance_chain output)
  const ARTEMIS_ACTION_TO_PHASE = {
    tool_call: 'tool_call',
    read: 'read_file',
    write: 'write_file',
    execute: 'execute_command',
    delegate: 'tool_call',
    reject: 'tool_call'
  };
  function normalizeArtemisChain(entries) {
    return entries.map(e => ({
      prov_id: e.prov_id,
      parent_prov_id: e.parent_prov_id !== undefined ? e.parent_prov_id : null,
      actor: e.agent_id || 'unknown',
      model: null,
      phase: e.kind === 'atp_prompt' ? 'atp_prompt' : e.target === 'atp_response' ? 'atp_response' : ARTEMIS_ACTION_TO_PHASE[e.action_type] || 'tool_call',
      input: e.kind === 'atp_prompt' ? {
        atp_context: e.atp_context
      } : {
        target: e.target
      },
      output: e.payload_summary ? {
        summary: e.payload_summary
      } : e.kind === 'atp_prompt' ? {
        summary: e.atp_context
      } : null,
      // The service's own status/error win; result (recording outcome) is a fallback.
      status: e.status === 'error' || e.result === 'error' ? 'error' : e.status === 'retry' || e.result === 'rejected' ? 'warn' : 'ok',
      error: e.error || (e.status === 'error' || e.result === 'error' ? e.payload_summary || 'error' : null),
      latency_ms: null,
      tags: e.kind === 'atp_prompt' ? ['atp', 'prompt'] : e.target === 'atp_response' ? ['atp', 'response', 'terminus'] : [e.action_type],
      timestamp: e.ts || null,
      body_sha256: e.body_sha256 || null,
      manifest_binding_id: e.manifest_binding_id || null,
      refs: e.refs || null,
      prev_action_hash: e.prev_action_hash || null,
      semantic_fingerprint: e.semantic_fingerprint || null,
      sequence_no: e.sequence_no != null ? e.sequence_no : null
    }));
  }

  // Build walk-back trail: response → ... → root (reverse lineage)
  function buildWalkBack(logs, parentProvId) {
    const root = logs.find(l => l.parent_prov_id === null && l.phase === 'atp_prompt');
    const response = logs.filter(l => l.phase === 'atp_response').pop();
    const children = logs.filter(l => l.parent_prov_id !== null);
    // Order: response first, then children reverse-chrono, then root
    const middle = children.filter(l => l.phase !== 'atp_response').slice().reverse();
    const trail = [];
    if (response) trail.push({
      ...response,
      walkRole: 'terminus'
    });
    middle.forEach(l => trail.push({
      ...l,
      walkRole: 'action'
    }));
    if (root) trail.push({
      ...root,
      walkRole: 'origin'
    });
    return trail;
  }

  // ═══════════════════════════════════════════════════════════
  // HEADER VALIDATION (compact — unchanged rules)
  // ═══════════════════════════════════════════════════════════

  const VALIDATION_RULES = {
    agent: {
      label: 'Agent_Profile',
      validate: v => !v ? {
        status: 'fail',
        msg: 'Required'
      } : !AGENT_PROFILES.includes(v) ? {
        status: 'warn',
        msg: 'Non-canonical agent'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    mode: {
      label: 'Mode',
      validate: v => !v ? {
        status: 'fail',
        msg: 'Required'
      } : !MODES.includes(v) ? {
        status: 'fail',
        msg: 'Invalid mode'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    context: {
      label: 'Context',
      validate: v => !v ? {
        status: 'fail',
        msg: 'Required'
      } : v.trim().length < 5 ? {
        status: 'warn',
        msg: 'Very short'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    priority: {
      label: 'Priority',
      validate: v => !v ? {
        status: 'fail',
        msg: 'Required'
      } : !PRIORITIES.includes(v) ? {
        status: 'fail',
        msg: 'Invalid'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    actionType: {
      label: 'Action Type',
      validate: v => !v ? {
        status: 'fail',
        msg: 'Required'
      } : !ACTION_TYPES.includes(v) ? {
        status: 'fail',
        msg: 'Invalid'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    targetZone: {
      label: 'TargetZone',
      validate: v => !v ? {
        status: 'warn',
        msg: 'Empty'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    specialInstructions: {
      label: 'Special Instructions',
      validate: v => !v ? {
        status: 'info',
        msg: 'Optional'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    },
    freeText: {
      label: 'Free_Text_Prompt',
      validate: v => !v ? {
        status: 'warn',
        msg: 'Empty'
      } : {
        status: 'pass',
        msg: 'OK'
      }
    }
  };
  const CROSS_VALIDATORS = [{
    id: 'encoding',
    label: 'Encoding Integrity',
    validate: h => /[\u200B-\u200F\u2028-\u202F\uFEFF\u00A0]/.test(Object.values(h).join('')) ? {
      status: 'fail',
      msg: 'Hidden Unicode detected!'
    } : {
      status: 'pass',
      msg: 'Clean'
    }
  }, {
    id: 'provid',
    label: 'ProvID in Header',
    validate: h => h.specialInstructions && /prov_id=/.test(h.specialInstructions) ? {
      status: 'pass',
      msg: 'Embedded'
    } : {
      status: 'info',
      msg: 'Added on mint'
    }
  }];
  function runValidation(header) {
    const fieldResults = {};
    for (const [key, rule] of Object.entries(VALIDATION_RULES)) fieldResults[key] = rule.validate(header[key]);
    const crossResults = CROSS_VALIDATORS.map(cv => ({
      ...cv,
      result: cv.validate(header)
    }));
    const all = [...Object.values(fieldResults), ...crossResults.map(c => c.result)];
    const passed = all.filter(r => r.status === 'pass').length;
    const infos = all.filter(r => r.status === 'info').length;
    const score = Math.round((passed + infos * 0.8) / all.length * 100);
    return {
      fieldResults,
      crossResults,
      score
    };
  }

  // ═══════════════════════════════════════════════════════════
  // UI COMPONENTS
  // ═══════════════════════════════════════════════════════════

  const StatusIcon = ({
    status
  }) => {
    const map = {
      pass: {
        char: '✓',
        color: 'text-emerald-400'
      },
      warn: {
        char: '⚠',
        color: 'text-amber-400'
      },
      fail: {
        char: '✕',
        color: 'text-red-400'
      },
      info: {
        char: 'ℹ',
        color: 'text-slate-500'
      },
      pending: {
        char: '○',
        color: 'text-slate-600'
      },
      active: {
        char: '◉',
        color: 'text-cyan-400 animate-pulse'
      },
      halt: {
        char: '⛔',
        color: 'text-red-500'
      }
    };
    const s = map[status] || map.info;
    return /*#__PURE__*/React.createElement("span", {
      className: `${s.color} text-xs font-bold w-4 inline-block shrink-0`
    }, s.char);
  };
  const LogEntry = ({
    entry,
    isNew,
    isParent,
    walkRole
  }) => {
    const Icon = phaseIcons[entry.phase] || GitBranch;
    const colors = phaseColors[entry.phase] || phaseColors.atp_prompt;
    return /*#__PURE__*/React.createElement("div", {
      className: `relative p-3 rounded-xl border transition-all duration-500 ${colors.border} bg-slate-800/80 backdrop-blur
      ${isNew ? `animate-pulse shadow-lg ${colors.glow}` : ''}
      ${isParent || walkRole === 'origin' ? 'ring-2 ring-violet-400 ring-offset-2 ring-offset-slate-900' : ''}
      ${walkRole === 'terminus' ? 'ring-2 ring-teal-400 ring-offset-2 ring-offset-slate-900' : ''}`
    }, (isParent || walkRole === 'origin') && /*#__PURE__*/React.createElement("div", {
      className: "absolute -top-2.5 left-4 px-2 py-0.5 bg-violet-500 text-white text-[10px] font-bold rounded-full"
    }, "ROOT / ORIGIN"), walkRole === 'terminus' && /*#__PURE__*/React.createElement("div", {
      className: "absolute -top-2.5 left-4 px-2 py-0.5 bg-teal-500 text-white text-[10px] font-bold rounded-full"
    }, "TERMINUS"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-start gap-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: `p-1.5 rounded-lg ${colors.bg} text-white shrink-0`
    }, /*#__PURE__*/React.createElement(Icon, {
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-w-0"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 flex-wrap"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-white text-sm capitalize"
    }, entry.phase.replace(/_/g, ' ')), /*#__PURE__*/React.createElement("span", {
      className: `px-2 py-0.5 rounded-full text-[10px] font-medium ${entry.status === 'ok' ? 'bg-emerald-500/20 text-emerald-400' : entry.status === 'warn' ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400'}`
    }, entry.status), entry.latency_ms != null && /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-1 text-[10px] text-slate-400"
    }, /*#__PURE__*/React.createElement(Clock, {
      size: 10
    }), " ", entry.latency_ms, "ms"), /*#__PURE__*/React.createElement("span", {
      className: "text-[10px] text-slate-500 ml-auto"
    }, entry.actor)), /*#__PURE__*/React.createElement("div", {
      className: "mt-1 text-[10px] text-slate-400 font-mono truncate"
    }, "prov_id: ", entry.prov_id ? entry.prov_id.slice(0, 8) + '…' : '—'), entry.parent_prov_id && /*#__PURE__*/React.createElement("div", {
      className: "text-[10px] text-slate-500 font-mono truncate"
    }, "↳ parent: ", entry.parent_prov_id.slice(0, 8), "…"), entry.body_sha256 && /*#__PURE__*/React.createElement("div", {
      className: "text-[10px] text-fuchsia-400/70 font-mono truncate"
    }, "⌗ sha256: ", entry.body_sha256.slice(0, 16), "…"), entry.manifest_binding_id && /*#__PURE__*/React.createElement("div", {
      className: "text-[10px] text-cyan-400/70 font-mono truncate"
    }, "binding: ", entry.manifest_binding_id.slice(0, 12), "… · refs=", entry.refs ? Object.values(entry.refs).filter(Boolean).length : 0, "/4", entry.sequence_no != null ? ` · seq=${entry.sequence_no}` : ''), entry.prev_action_hash && /*#__PURE__*/React.createElement("div", {
      className: "text-[10px] text-violet-400/70 font-mono truncate"
    }, "↤ prev: ", entry.prev_action_hash.slice(0, 16), "…"), entry.tags?.length > 0 && /*#__PURE__*/React.createElement("div", {
      className: "mt-1.5 flex flex-wrap gap-1"
    }, entry.tags.map((tag, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      className: "px-1.5 py-0.5 bg-slate-700 text-slate-300 rounded text-[10px]"
    }, tag))), entry.input && /*#__PURE__*/React.createElement("div", {
      className: "mt-1.5 p-1.5 bg-slate-900/50 rounded text-[10px] text-slate-400 font-mono truncate"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "in:"), " ", JSON.stringify(entry.input)), entry.output && /*#__PURE__*/React.createElement("div", {
      className: "mt-1 p-1.5 bg-slate-900/50 rounded text-[10px] text-emerald-400 font-mono truncate"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "out:"), " ", JSON.stringify(entry.output)), entry.error && /*#__PURE__*/React.createElement("div", {
      className: "mt-1 p-1.5 bg-red-900/30 rounded text-[10px] text-red-400 font-mono truncate"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-red-500"
    }, "err:"), " ", String(entry.error)))));
  };
  const TreeView = ({
    logs,
    parentId
  }) => {
    const parent = logs.find(l => l.prov_id === parentId);
    const children = logs.filter(l => l.parent_prov_id === parentId);
    if (!parent) return null;
    const Icon = phaseIcons[parent.phase] || GitBranch;
    const colors = phaseColors[parent.phase] || phaseColors.atp_prompt;
    return /*#__PURE__*/React.createElement("div", {
      className: "relative"
    }, /*#__PURE__*/React.createElement("div", {
      className: `inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border ${colors.border} bg-slate-800/60 text-white text-xs font-medium`
    }, /*#__PURE__*/React.createElement(Icon, {
      size: 12,
      className: colors.text
    }), parent.phase.replace(/_/g, ' '), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500 font-mono text-[10px]"
    }, parent.prov_id.slice(0, 6))), children.length > 0 && /*#__PURE__*/React.createElement("div", {
      className: "ml-4 mt-1.5 pl-3 border-l-2 border-slate-600 space-y-1.5"
    }, children.map(child => /*#__PURE__*/React.createElement(TreeView, {
      key: child.prov_id,
      logs: logs,
      parentId: child.prov_id
    }))));
  };
  const Stats = ({
    logs
  }) => {
    const s = {
      total: logs.length,
      reads: logs.filter(l => l.phase === 'read_file').length,
      writes: logs.filter(l => l.phase === 'write_file').length,
      executes: logs.filter(l => l.phase === 'execute_command').length,
      tools: logs.filter(l => l.phase === 'tool_call').length,
      errors: logs.filter(l => l.status === 'error').length
    };
    return /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-2"
    }, [{
      label: 'Total',
      value: s.total,
      color: 'text-violet-400'
    }, {
      label: 'Reads',
      value: s.reads,
      color: 'text-sky-400'
    }, {
      label: 'Writes',
      value: s.writes,
      color: 'text-emerald-400'
    }, {
      label: 'Cmds',
      value: s.executes,
      color: 'text-amber-400'
    }, {
      label: 'Tools',
      value: s.tools,
      color: 'text-rose-400'
    }, {
      label: 'Errors',
      value: s.errors,
      color: s.errors > 0 ? 'text-red-400' : 'text-slate-500'
    }].map((x, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "bg-slate-800/50 rounded-lg p-2 text-center"
    }, /*#__PURE__*/React.createElement("div", {
      className: `text-lg font-bold ${x.color}`
    }, x.value), /*#__PURE__*/React.createElement("div", {
      className: "text-[10px] text-slate-400"
    }, x.label))));
  };

  // ── Session Governance Report (for Claude session snapshots) ──

  const SessionReport = ({
    session
  }) => {
    const g = session.governance;
    const bypassing = g.permissionMode === 'bypassPermissions';
    const fmtTime = ms => ms ? new Date(ms).toLocaleString() : '—';
    return /*#__PURE__*/React.createElement("div", {
      className: "space-y-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: `p-4 rounded-xl border-2 ${bypassing ? 'border-red-500/50 bg-red-500/10' : 'border-emerald-500/40 bg-emerald-500/5'}`
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-2"
    }, bypassing ? /*#__PURE__*/React.createElement(AlertTriangle, {
      size: 18,
      className: "text-red-400"
    }) : /*#__PURE__*/React.createElement(Shield, {
      size: 18,
      className: "text-emerald-400"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-sm"
    }, "Governance Posture")), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 md:grid-cols-3 gap-2 text-xs"
    }, /*#__PURE__*/React.createElement("div", {
      className: `p-2 rounded-lg ${bypassing ? 'bg-red-500/20 border border-red-500/30' : 'bg-slate-800/60'}`
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase"
    }, "Permission Mode"), /*#__PURE__*/React.createElement("div", {
      className: `font-mono font-bold ${bypassing ? 'text-red-400' : 'text-emerald-400'}`
    }, g.permissionMode), bypassing && /*#__PURE__*/React.createElement("div", {
      className: "text-red-400/80 text-[10px] mt-1"
    }, "⚠ Sandbox enforcement bypassed — GOVERNANCE.md violation-tracking inactive")), /*#__PURE__*/React.createElement("div", {
      className: "p-2 rounded-lg bg-slate-800/60"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase"
    }, "Exec Policies"), /*#__PURE__*/React.createElement("div", {
      className: `font-mono font-bold ${g.execPolicies === 0 ? 'text-amber-400' : 'text-emerald-400'}`
    }, g.execPolicies === 0 ? 'none defined' : g.execPolicies)), /*#__PURE__*/React.createElement("div", {
      className: "p-2 rounded-lg bg-slate-800/60"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase"
    }, "Host Loop"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono font-bold text-slate-300"
    }, g.hostLoopMode ? 'enabled' : 'off')), /*#__PURE__*/React.createElement("div", {
      className: "p-2 rounded-lg bg-slate-800/60"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase"
    }, "Memory / Skills / Plugins"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-slate-300"
    }, [g.memoryEnabled && 'mem', g.skillsEnabled && 'skills', g.pluginsEnabled && 'plugins'].filter(Boolean).join(' · ') || 'none')))), /*#__PURE__*/React.createElement("div", {
      className: "p-4 rounded-xl border border-slate-700 bg-slate-800/50"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-3"
    }, /*#__PURE__*/React.createElement(Link2, {
      size: 16,
      className: "text-violet-400"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-sm"
    }, "Identity Chain (walk-back)")), /*#__PURE__*/React.createElement("div", {
      className: "space-y-1.5"
    }, [{
      icon: User,
      label: 'Account',
      value: session.identity.account,
      note: 'who'
    }, {
      icon: Zap,
      label: 'Model',
      value: session.identity.model,
      note: 'actor'
    }, {
      icon: GitBranch,
      label: 'Session ID',
      value: session.identity.sessionId,
      note: 'parent scope'
    }, {
      icon: GitBranch,
      label: 'CLI Session',
      value: session.identity.cliSessionId,
      note: 'child scope'
    }, {
      icon: Server,
      label: 'VM Process',
      value: session.identity.processName,
      note: 'execution container'
    }, {
      icon: Folder,
      label: 'CWD',
      value: session.scope.cwd,
      note: 'TargetZone'
    }].map((row, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "flex items-center gap-2 text-xs"
    }, /*#__PURE__*/React.createElement(row.icon, {
      size: 12,
      className: "text-slate-500 shrink-0"
    }), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400 w-24 shrink-0"
    }, row.label), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-slate-300 truncate flex-1"
    }, row.value), /*#__PURE__*/React.createElement("span", {
      className: "text-[10px] text-slate-600 shrink-0"
    }, row.note))))), /*#__PURE__*/React.createElement("div", {
      className: "p-4 rounded-xl border border-slate-700 bg-slate-800/50"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-3"
    }, /*#__PURE__*/React.createElement(Globe, {
      size: 16,
      className: "text-cyan-400"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-sm"
    }, "Scope Grants")), /*#__PURE__*/React.createElement("div", {
      className: "grid md:grid-cols-2 gap-3 text-xs"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase mb-1"
    }, "Selected Folders (", session.scope.selectedFolders.length, ")"), session.scope.selectedFolders.map((f, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "font-mono text-slate-300 truncate"
    }, f))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase mb-1"
    }, "WebFetch Allowed (", session.scope.webFetchUrls.length, ")"), session.scope.webFetchUrls.map((u, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "font-mono text-slate-300 truncate"
    }, u))), /*#__PURE__*/React.createElement("div", {
      className: "md:col-span-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-400 text-[10px] uppercase mb-1"
    }, "Egress Domains (", session.scope.egressDomains.length, ")"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap gap-1"
    }, session.scope.egressDomains.map((d, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      className: "px-1.5 py-0.5 bg-slate-700 text-slate-300 rounded text-[10px] font-mono"
    }, d)))))), /*#__PURE__*/React.createElement("div", {
      className: "p-4 rounded-xl border border-slate-700 bg-slate-800/50"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-3"
    }, /*#__PURE__*/React.createElement(Database, {
      size: 16,
      className: "text-rose-400"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-sm"
    }, "Tool Surface"), /*#__PURE__*/React.createElement("span", {
      className: "ml-auto text-xs text-slate-400"
    }, session.toolSurface.enabledToolCount, " MCP tools · ", session.toolSurface.slashCommands, " skills")), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap gap-1.5"
    }, session.toolSurface.mcpServers.map((s, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      className: "px-2 py-1 bg-slate-700/70 rounded-lg text-[11px] text-slate-300 flex items-center gap-1.5"
    }, /*#__PURE__*/React.createElement(Server, {
      size: 10,
      className: "text-slate-500"
    }), s.name, s.toolCount > 0 && /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "(", s.toolCount, ")"))))), /*#__PURE__*/React.createElement("div", {
      className: "p-4 rounded-xl border border-slate-700 bg-slate-800/50"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-2"
    }, /*#__PURE__*/React.createElement(Clock, {
      size: 16,
      className: "text-amber-400"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-semibold text-sm"
    }, "Session Timeline")), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-2 text-xs"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-500 text-[10px] uppercase"
    }, "Created"), /*#__PURE__*/React.createElement("div", {
      className: "text-slate-300"
    }, fmtTime(session.timeline.createdAt))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-500 text-[10px] uppercase"
    }, "Last Activity"), /*#__PURE__*/React.createElement("div", {
      className: "text-slate-300"
    }, fmtTime(session.timeline.lastActivityAt))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-500 text-[10px] uppercase"
    }, "Duration"), /*#__PURE__*/React.createElement("div", {
      className: "text-slate-300"
    }, session.timeline.durationHrs ? `${session.timeline.durationHrs} hrs` : '—'))), /*#__PURE__*/React.createElement("div", {
      className: "mt-2 text-[10px] text-slate-500"
    }, /*#__PURE__*/React.createElement("span", {
      className: "uppercase"
    }, "Title:"), " ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400"
    }, session.identity.title))), /*#__PURE__*/React.createElement("div", {
      className: "p-3 rounded-xl border border-amber-500/20 bg-amber-500/5 text-xs text-amber-300/90 flex items-start gap-2"
    }, /*#__PURE__*/React.createElement(AlertTriangle, {
      size: 14,
      className: "shrink-0 mt-0.5"
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "font-semibold"
    }, "Provenance gap:"), " this session snapshot declares scope and posture but contains no agent_logs — the action-level chain (tool calls, reads, writes) is not in this file. To walk back individual actions, export the agent_logs table for sessionId ", /*#__PURE__*/React.createElement("span", {
      className: "font-mono"
    }, session.identity.sessionId.slice(0, 20), "…"), " and import it here.")));
  };

  // ═══════════════════════════════════════════════════════════
  // MAIN
  // ═══════════════════════════════════════════════════════════

  function ATPMissionControl() {
    const [header, setHeader] = useState({
      agent: 'Claude-Code',
      mode: 'Synthesize',
      context: 'Navigate the knowledge graph',
      priority: 'Normal',
      actionType: 'Reflect',
      targetZone: '/workspace/project',
      specialInstructions: '',
      outputType: 'inline chat',
      freeText: 'ATP Mission Control'
    });
    const [serviceUrl, setServiceUrl] = useState(DEFAULT_PROVENANCE_URL);
    const [serviceStatus, setServiceStatus] = useState('unknown');
    const [parentProvId, setParentProvId] = useState(null);
    const [sourceMode, setSourceMode] = useState(null); // 'live' | 'simulation' | 'import'
    const [logs, setLogs] = useState([]);
    const [chainState, setChainState] = useState(Object.fromEntries(PROVENANCE_STEPS.map(s => [s.id, 'pending'])));
    const [isRunning, setIsRunning] = useState(false);
    const [actionIndex, setActionIndex] = useState(0);
    const [newLogId, setNewLogId] = useState(null);
    const [view, setView] = useState('timeline'); // timeline | walkback | json
    const [importedSession, setImportedSession] = useState(null);
    const [chainProfile, setChainProfile] = useState('skill'); // 'skill' | 'artemis'
    const [importError, setImportError] = useState(null);
    const [liveError, setLiveError] = useState(null);
    const [attachId, setAttachId] = useState('');
    const [runtimeSessionId] = useState(() => {
      try {
        const stored = sessionStorage.getItem('atp_runtime_session_id');
        if (stored) return stored;
        const created = generateUUID();
        sessionStorage.setItem('atp_runtime_session_id', created);
        return created;
      } catch {
        return generateUUID();
      }
    });
    const [manifestBindingId] = useState(() => {
      try {
        const stored = sessionStorage.getItem('atp_manifest_binding_id');
        if (stored) return stored;
        const created = generateUUID();
        sessionStorage.setItem('atp_manifest_binding_id', created);
        return created;
      } catch {
        return generateUUID();
      }
    });
    const fileInputRef = useRef(null);
    // Schema result for imported agent_logs, taken from the raw records before
    // normalizeLogs fills display defaults. null = not an agent_logs import.
    const [rawSchemaValid, setRawSchemaValid] = useState(null);
    // Bumped whenever the live polling effect is torn down, so a /chain
    // response that resolves after the user switches chains is dropped.
    const liveChainGenRef = useRef(0);
    const validation = useMemo(() => runValidation(header), [header]);

    // Live chain enforcement (Steps 4-8) — reacts to log changes
    useEffect(() => {
      if (logs.length === 0) return;
      const schemaOk = logs.every(l => validateLogSchema(l).valid) && rawSchemaValid !== false;
      const integrity = validateChainIntegrity(logs, parentProvId);
      const hasChildren = logs.some(l => l.parent_prov_id !== null);
      const hasRoot = logs.some(l => l.parent_prov_id === null && l.phase === 'atp_prompt');
      const errorEntries = logs.filter(l => l.status === 'error');
      const isArtemis = chainProfile === 'artemis';
      setChainState(prev => ({
        ...prev,
        mint_parent: hasRoot && prev.mint_parent === 'pending' ? 'pass' : prev.mint_parent,
        log_prompt: hasRoot && prev.log_prompt === 'pending' ? 'pass' : prev.log_prompt,
        log_actions: hasChildren ? 'pass' : prev.log_actions,
        log_errors: errorEntries.length > 0 ? errorEntries.every(l => l.parent_prov_id !== undefined && l.parent_prov_id !== null) ? 'pass' : 'fail' : hasChildren ? 'pass' : prev.log_errors,
        // Artemis MCP schema has no atp_response kind — last action is terminus (warn, counts complete)
        log_response: integrity.hasResponse ? 'pass' : isArtemis && hasChildren ? 'warn' : prev.log_response,
        schema_valid: schemaOk ? 'pass' : 'warn',
        chain_complete: isArtemis ? integrity.exactlyOneParent && integrity.noOrphans && hasChildren ? 'pass' : integrity.orphanCount > 0 ? 'fail' : prev.chain_complete : integrity.valid && integrity.hasResponse ? 'pass' : integrity.orphanCount > 0 ? 'fail' : prev.chain_complete
      }));
    }, [logs, parentProvId, chainProfile, rawSchemaValid]);

    // ── JSON Import handler ──────────────────────────────────

    const handleImport = useCallback((jsonText, filename) => {
      setImportError(null);
      let data;
      try {
        data = JSON.parse(jsonText);
      } catch (e) {
        setImportError(`Invalid JSON: ${e.message}`);
        return;
      }
      const format = detectImportFormat(data);
      if (format === 'agent_logs' || format === 'agent_logs_wrapped' || format === 'artemis_chain') {
        const raw = format === 'agent_logs_wrapped' ? data.logs : data;
        // Validate what the file actually contains; normalization below fills
        // missing fields with display defaults and would hide the gaps.
        setRawSchemaValid(format === 'artemis_chain' ? null : raw.every(l => l !== null && typeof l === 'object' && validateLogSchema(l).valid));
        const normalized = format === 'artemis_chain' ? normalizeArtemisChain(raw) : normalizeLogs(raw);
        const root = normalized.find(l => l.parent_prov_id === null && l.phase === 'atp_prompt');
        const pid = root ? root.prov_id : normalized[0]?.parent_prov_id || null;
        setImportedSession(null);
        setLogs(normalized);
        setParentProvId(pid);
        setSourceMode('import');
        setIsRunning(false);
        setView('walkback');
        setChainProfile(format === 'artemis_chain' ? 'artemis' : 'skill');

        // Retroactive chain validation on imported data
        setChainState({
          mint_parent: pid ? 'pass' : 'fail',
          // Artemis profile: atp_context bound at mint replaces header-embed verification
          embed_header: format === 'artemis_chain' ? 'pass' : 'info',
          log_prompt: root ? 'pass' : 'fail',
          log_actions: 'pending',
          // useEffect recomputes
          log_errors: 'pending',
          log_response: 'pending',
          schema_valid: 'pending',
          chain_complete: 'pending'
        });
      } else if (format === 'claude_session') {
        const session = parseSessionSnapshot(data);
        setRawSchemaValid(null);
        setImportedSession(session);
        setLogs([]);
        setParentProvId(session.identity.sessionId);
        setSourceMode('import');
        setIsRunning(false);
        setView('session');
        // Session snapshots have no action chain — mark what we CAN verify
        setChainState({
          mint_parent: 'pass',
          // sessionId exists = identity minted
          embed_header: 'info',
          // N/A for session files
          log_prompt: session.initialMessage ? 'pass' : 'warn',
          log_actions: 'fail',
          // the gap: no agent_logs in this file
          log_errors: 'pending',
          log_response: 'fail',
          schema_valid: 'info',
          chain_complete: 'fail' // chain not reconstructable from snapshot alone
        });
      } else {
        setImportError(`Unrecognized format. Expected an agent_logs array (entries with prov_id) or a Claude session snapshot (sessionId + permissionMode). Got: ${format}`);
      }
    }, []);
    const onFileSelected = useCallback(e => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = ev => handleImport(ev.target.result, file.name);
      reader.onerror = () => setImportError('Failed to read file');
      reader.readAsText(file);
      e.target.value = '';
    }, [handleImport]);

    // ── Live service ─────────────────────────────────────────

    const checkHealth = useCallback(async () => {
      setServiceStatus('checking');
      try {
        const resp = await fetch(`${serviceUrl}/health`, {
          signal: AbortSignal.timeout(5000)
        });
        setServiceStatus(resp.ok ? 'connected' : 'error');
      } catch {
        setServiceStatus('error');
      }
    }, [serviceUrl]);

    // Poll the service so worker actions become visible in the live timeline.
    const refreshLiveChain = useCallback(async () => {
      if (sourceMode !== 'live' || !parentProvId) return;
      const generation = liveChainGenRef.current;
      const isStale = () => generation !== liveChainGenRef.current;
      try {
        const resp = await fetch(`${serviceUrl}/chain?parent_prov_id=${encodeURIComponent(parentProvId)}`, {
          signal: AbortSignal.timeout(5000)
        });
        if (isStale()) return;
        if (!resp.ok) throw new Error(`chain request failed (${resp.status})`);
        const remoteLogs = normalizeArtemisChain(await resp.json());
        if (isStale()) return;
        setLogs(previous => {
          const existing = new Map(previous.map(entry => [entry.prov_id, entry]));
          const added = [];
          remoteLogs.forEach(entry => {
            if (!existing.has(entry.prov_id)) added.push(entry);
            existing.set(entry.prov_id, entry);
          });
          if (added.length > 0) {
            setNewLogId(added[added.length - 1].prov_id);
            setTimeout(() => setNewLogId(null), 1000);
          }
          return Array.from(existing.values()).sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
        });
        setChainProfile('artemis');
        setLiveError(null);
        setServiceStatus('connected');
      } catch (error) {
        if (isStale()) return;
        setLiveError(`Live log stream unavailable: ${error.message}`);
        setServiceStatus('error');
      }
    }, [parentProvId, serviceUrl, sourceMode]);
    useEffect(() => {
      if (sourceMode !== 'live' || !parentProvId) return;
      refreshLiveChain();
      const timer = setInterval(refreshLiveChain, 1500);
      return () => {
        clearInterval(timer);
        // Invalidate in-flight /chain requests for the chain being left.
        liveChainGenRef.current += 1;
      };
    }, [parentProvId, refreshLiveChain, sourceMode]);

    // Attach to an existing chain: no local root is synthesized — the service's
    // persisted rows are the single source of truth, streamed in by the poll.
    const attachToChain = useCallback(() => {
      const pid = attachId.trim();
      if (!pid) return;
      setImportedSession(null);
      setImportError(null);
      setLiveError(null);
      setLogs([]);
      setActionIndex(0);
      setIsRunning(false);
      setChainProfile('artemis');
      setRawSchemaValid(null);
      setSourceMode('live');
      setParentProvId(pid);
      setView('timeline');
      setChainState({
        mint_parent: 'pass',
        embed_header: 'info',
        log_prompt: 'pending',
        log_actions: 'pending',
        log_errors: 'pending',
        log_response: 'pending',
        schema_valid: 'pending',
        chain_complete: 'pending'
      });
    }, [attachId]);
    const bindManifestLayers = useCallback(async () => {
      const metadataResp = await fetch(`${serviceUrl}/runtime/metadata`, {
        signal: AbortSignal.timeout(5000)
      });
      if (!metadataResp.ok) throw new Error(`runtime metadata failed (${metadataResp.status})`);
      const metadata = await metadataResp.json();
      const layers = [
        ['declaration', {
          identity: { agent_id: header.agent },
          evidence_roots: { provenance_location: serviceUrl }
        }],
        ['version', metadata],
        ['session', {
          session_id: runtimeSessionId,
          scope: { workspace: header.targetZone, isolation_mode: 'browser' },
          effective_policy: { network_policy: new URL(serviceUrl).origin },
          execution_location: { placement: 'local-browser' }
        }],
        ['route', {
          health: { last_verified: new Date().toISOString() }
        }]
      ];
      const refs = {};
      let parentRef = null;
      for (const [layer, body] of layers) {
        const resp = await fetch(`${serviceUrl}/manifest/bind`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            layer,
            body,
            parent_ref: parentRef,
            manifest_binding_id: manifestBindingId,
            session_id: runtimeSessionId
          }),
          signal: AbortSignal.timeout(5000)
        });
        if (!resp.ok) throw new Error(`manifest ${layer} bind failed (${resp.status})`);
        const result = await resp.json();
        refs[`${layer}_ref`] = result.layer_hash;
        parentRef = result.layer_hash;
      }
      return refs;
    }, [header.agent, header.targetZone, manifestBindingId, runtimeSessionId, serviceUrl]);
    const startChain = useCallback(async mode => {
      setImportedSession(null);
      setLogs([]);
      setActionIndex(0);
      setChainState(Object.fromEntries(PROVENANCE_STEPS.map(s => [s.id, 'pending'])));
      setRawSchemaValid(null);
      setSourceMode(mode);
      setLiveError(null);
      setChainProfile('skill');
      setView('timeline');
      setChainState(prev => ({
        ...prev,
        mint_parent: 'active'
      }));
      let pid = null;
      let mintData = null;
      if (mode === 'live') {
        try {
          // Bind L0–L3 first: /mint requires a complete manifest binding, and
          // child actions logged under the same binding id resolve against it.
          await bindManifestLayers();
        } catch (error) {
          setLiveError(error.message);
          setChainState(prev => ({ ...prev, mint_parent: 'halt' }));
          return;
        }
        try {
          // Single-call mint: the service stores a complete, correctly-typed,
          // manifest-bound atp_prompt root from this payload (no /log overwrite).
          const resp = await fetch(`${serviceUrl}/mint`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              agent_id: header.agent,
              actor: header.agent,
              atp_context: header.context,
              input: {
                prompt: header.freeText,
                context: [header.context],
                mode: header.mode
              },
              tags: ['atp', 'prompt'],
              manifest_binding_id: manifestBindingId
            }),
            signal: AbortSignal.timeout(5000)
          });
          if (resp.ok) {
            mintData = await resp.json();
            pid = mintData.prov_id || mintData.id;
          }
        } catch {/* halt below */}
        if (!pid) {
          setChainState(prev => ({
            ...prev,
            mint_parent: 'halt'
          }));
          return;
        }
      } else {
        pid = generateUUID();
      }
      setParentProvId(pid);
      setChainState(prev => ({
        ...prev,
        mint_parent: mode === 'live' ? 'pass' : 'warn'
      }));
      setHeader(prev => ({
        ...prev,
        specialInstructions: prev.specialInstructions && !/prov_id=/.test(prev.specialInstructions) ? `${prev.specialInstructions}; prov_id=${pid}` : `prov_id=${pid}`
      }));
      setChainState(prev => ({
        ...prev,
        embed_header: 'pass'
      }));
      // Provisional root for immediate display. In live mode the /chain poll
      // replaces it with the service's persisted row (the source of truth)
      // within one polling interval.
      const rootEntry = {
        prov_id: pid,
        parent_prov_id: null,
        actor: mintData && mintData.actor || header.agent,
        model: mintData && mintData.model || null,
        phase: 'atp_prompt',
        input: {
          prompt: header.freeText,
          context: [header.context],
          mode: header.mode
        },
        output: {
          summary: mode === 'live' ? mintData && mintData.atp_context || header.context : 'ATP header emitted, workflow initiated'
        },
        status: 'ok',
        latency_ms: mode === 'live' ? null : 12,
        tags: ['atp', 'prompt'],
        timestamp: mintData && mintData.ts || new Date().toISOString(),
        manifest_binding_id: mode === 'live' ? manifestBindingId : null,
        refs: null,
        canonical_action: null,
        semantic_fingerprint: null,
        prev_action_hash: null
      };
      setLogs([rootEntry]);
      setNewLogId(pid);
      setChainState(prev => ({
        ...prev,
        log_prompt: 'pass',
        log_actions: 'active'
      }));
      setTimeout(() => setNewLogId(null), 1000);
      if (mode === 'simulation') setIsRunning(true);
    }, [bindManifestLayers, header, manifestBindingId, serviceUrl]);

    // Simulation engine
    const addChildLog = useCallback(() => {
      if (actionIndex >= simulatedActions.length) {
        const responseEntry = {
          prov_id: generateUUID(),
          parent_prov_id: parentProvId,
          actor: header.agent,
          model: 'claude-opus-4-6',
          phase: 'atp_response',
          input: null,
          output: {
            summary: 'All actions completed',
            actions_count: simulatedActions.length
          },
          status: 'ok',
          latency_ms: 8,
          tags: ['atp', 'response'],
          timestamp: new Date().toISOString()
        };
        setLogs(prev => [...prev, responseEntry]);
        setNewLogId(responseEntry.prov_id);
        setIsRunning(false);
        setTimeout(() => setNewLogId(null), 1000);
        return;
      }
      const action = simulatedActions[actionIndex];
      const entry = {
        prov_id: generateUUID(),
        parent_prov_id: parentProvId,
        actor: action.phase === 'tool_call' ? `mcp_${action.input.tool}` : header.agent,
        model: 'claude-opus-4-6',
        phase: action.phase,
        input: action.input,
        output: action.output,
        status: 'ok',
        latency_ms: Math.floor(Math.random() * 200) + 10,
        tags: action.tags,
        timestamp: new Date().toISOString()
      };
      setLogs(prev => [...prev, entry]);
      setNewLogId(entry.prov_id);
      setActionIndex(prev => prev + 1);
      setTimeout(() => setNewLogId(null), 1000);
    }, [actionIndex, parentProvId, header.agent]);
    useEffect(() => {
      if (!isRunning || !parentProvId) return;
      const timer = setTimeout(addChildLog, 1200);
      return () => clearTimeout(timer);
    }, [isRunning, logs.length, parentProvId, addChildLog]);
    const reset = useCallback(() => {
      setLogs([]);
      setActionIndex(0);
      setIsRunning(false);
      setNewLogId(null);
      setParentProvId(null);
      setRawSchemaValid(null);
      setSourceMode(null);
      setLiveError(null);
      setImportedSession(null);
      setImportError(null);
      setView('timeline');
      setChainProfile('skill');
      setChainState(Object.fromEntries(PROVENANCE_STEPS.map(s => [s.id, 'pending'])));
      setHeader(prev => ({
        ...prev,
        specialInstructions: prev.specialInstructions.replace(/;?\s*prov_id=[^;]*/g, '').trim()
      }));
    }, []);
    const updateHeader = (field, value) => setHeader(prev => ({
      ...prev,
      [field]: value
    }));
    const completedSteps = Object.values(chainState).filter(s => s === 'pass' || s === 'warn').length;
    const chainScore = Math.round(completedSteps / PROVENANCE_STEPS.length * 100);
    const walkBackTrail = useMemo(() => logs.length > 0 ? buildWalkBack(logs, parentProvId) : [], [logs, parentProvId]);
    return /*#__PURE__*/React.createElement("div", {
      className: "min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-violet-950 text-white p-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "max-w-7xl mx-auto space-y-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-center space-y-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "inline-flex items-center gap-2 px-4 py-2 bg-violet-500/20 border border-violet-500/50 rounded-full text-violet-300 text-sm"
    }, /*#__PURE__*/React.createElement(Zap, {
      size: 16
    }), " ATP Mission Control"), /*#__PURE__*/React.createElement("h1", {
      className: "text-3xl font-bold bg-gradient-to-r from-violet-400 via-sky-400 to-emerald-400 bg-clip-text text-transparent"
    }, "Provenance-Validated Control Plane"), /*#__PURE__*/React.createElement("p", {
      className: "text-slate-400 max-w-2xl mx-auto text-sm"
    }, "Build, validate, monitor — or import a JSON export and walk back through the provenance chain.")), /*#__PURE__*/React.createElement("div", {
      className: "flex justify-center gap-2 flex-wrap"
    }, /*#__PURE__*/React.createElement("span", {
      className: `px-3 py-1 rounded-full text-xs font-medium ${validation.score >= 80 ? 'bg-emerald-500/20 text-emerald-400' : validation.score >= 50 ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400'}`
    }, "🛡️ Header ", validation.score, "%"), /*#__PURE__*/React.createElement("span", {
      className: `px-3 py-1 rounded-full text-xs font-medium ${chainScore >= 80 ? 'bg-emerald-500/20 text-emerald-400' : chainScore > 0 ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-700 text-slate-500'}`
    }, "🔗 Chain ", completedSteps, "/", PROVENANCE_STEPS.length), /*#__PURE__*/React.createElement("span", {
      className: `px-3 py-1 rounded-full text-xs font-medium ${parentProvId ? 'bg-violet-500/20 text-violet-300' : 'bg-slate-700 text-slate-500'}`
    }, parentProvId ? `id: ${String(parentProvId).slice(0, 14)}…` : 'No ProvID'), sourceMode && /*#__PURE__*/React.createElement("span", {
      className: `px-3 py-1 rounded-full text-xs font-medium ${sourceMode === 'live' ? 'bg-emerald-500/20 text-emerald-400' : sourceMode === 'import' ? 'bg-sky-500/20 text-sky-400' : 'bg-amber-500/20 text-amber-400'}`
    }, sourceMode === 'live' ? '📡 Live' : sourceMode === 'import' ? '📥 Imported' : '🧪 Simulation'), /*#__PURE__*/React.createElement("span", {
      className: `px-3 py-1 rounded-full text-xs font-medium ${serviceStatus === 'connected' ? 'bg-emerald-500/20 text-emerald-400' : serviceStatus === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-slate-700 text-slate-500'}`
    }, serviceStatus === 'connected' ? '● Service Up' : serviceStatus === 'error' ? '● Service Down' : '○ Service')), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-center gap-3 flex-wrap"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => startChain('simulation'),
      disabled: isRunning,
      className: `flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-all ${isRunning ? 'bg-slate-700 text-slate-400 cursor-not-allowed' : 'bg-gradient-to-r from-violet-500 to-sky-500 hover:from-violet-400 hover:to-sky-400 shadow-lg shadow-violet-500/25'}`
    }, /*#__PURE__*/React.createElement(Play, {
      size: 16
    }), " Simulate"), /*#__PURE__*/React.createElement("button", {
      onClick: () => startChain('live'),
      disabled: isRunning || serviceStatus !== 'connected',
      className: `flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-all ${isRunning || serviceStatus !== 'connected' ? 'bg-slate-700 text-slate-400 cursor-not-allowed' : 'bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 shadow-lg shadow-emerald-500/25'}`
    }, /*#__PURE__*/React.createElement(Radio, {
      size: 16
    }), " Live Chain"), /*#__PURE__*/React.createElement("button", {
      onClick: () => fileInputRef.current?.click(),
      className: "flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-sky-500 to-cyan-500 hover:from-sky-400 hover:to-cyan-400 shadow-lg shadow-sky-500/25 transition-all"
    }, /*#__PURE__*/React.createElement(Upload, {
      size: 16
    }), " Import JSON"), /*#__PURE__*/React.createElement("input", {
      ref: fileInputRef,
      type: "file",
      accept: ".json,application/json",
      onChange: onFileSelected,
      className: "hidden"
    }), /*#__PURE__*/React.createElement("button", {
      onClick: () => setIsRunning(false),
      disabled: !isRunning,
      className: `flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm transition-all ${!isRunning ? 'bg-slate-700 text-slate-400 cursor-not-allowed' : 'bg-amber-500/20 border border-amber-500/50 text-amber-300 hover:bg-amber-500/30'}`
    }, /*#__PURE__*/React.createElement(Pause, {
      size: 16
    })), /*#__PURE__*/React.createElement("button", {
      onClick: reset,
      className: "flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm bg-slate-800 border border-slate-600 hover:bg-slate-700 transition-all"
    }, /*#__PURE__*/React.createElement(RotateCcw, {
      size: 16
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("input", {
      type: "text",
      value: serviceUrl,
      onChange: e => setServiceUrl(e.target.value),
      className: "bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-300 font-mono w-48 focus:border-cyan-500 focus:outline-none",
      placeholder: DEFAULT_PROVENANCE_URL
    }), /*#__PURE__*/React.createElement("button", {
      onClick: checkHealth,
      className: "px-3 py-2 rounded-lg bg-cyan-500/20 text-cyan-400 text-xs border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors"
    }, "Check")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("input", {
      type: "text",
      value: attachId,
      onChange: e => setAttachId(e.target.value),
      onKeyDown: e => {
        if (e.key === 'Enter') attachToChain();
      },
      className: "bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-300 font-mono w-72 focus:border-emerald-500 focus:outline-none",
      placeholder: "parent prov_id — watch existing chain"
    }), /*#__PURE__*/React.createElement("button", {
      onClick: attachToChain,
      disabled: !attachId.trim() || serviceStatus !== 'connected',
      className: `px-3 py-2 rounded-lg text-xs border transition-colors ${!attachId.trim() || serviceStatus !== 'connected' ? 'bg-slate-700 text-slate-500 border-slate-600 cursor-not-allowed' : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/30'}`
    }, "Watch Live"))), (importError || liveError) && /*#__PURE__*/React.createElement("div", {
      className: "max-w-2xl mx-auto p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-300 text-sm flex items-start gap-2"
    }, /*#__PURE__*/React.createElement(AlertTriangle, {
      size: 16,
      className: "shrink-0 mt-0.5"
    }), " ", importError || liveError), /*#__PURE__*/React.createElement("div", {
      className: "grid lg:grid-cols-3 gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "space-y-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/50 backdrop-blur rounded-2xl border border-slate-700 p-4"
    }, /*#__PURE__*/React.createElement("h3", {
      className: "text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3"
    }, "⚙️ ATP Header"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-2"
    }, [{
      label: 'Agent_Profile',
      field: 'agent',
      options: AGENT_PROFILES
    }, {
      label: 'Mode',
      field: 'mode',
      options: MODES
    }, {
      label: 'Priority',
      field: 'priority',
      options: PRIORITIES
    }, {
      label: 'Action Type',
      field: 'actionType',
      options: ACTION_TYPES
    }].map(f => /*#__PURE__*/React.createElement("div", {
      key: f.field,
      className: "flex flex-col gap-1"
    }, /*#__PURE__*/React.createElement("label", {
      className: "text-[10px] text-slate-400 font-mono"
    }, "[[", f.label, "]]"), /*#__PURE__*/React.createElement("select", {
      value: header[f.field],
      onChange: e => updateHeader(f.field, e.target.value),
      className: "bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:border-violet-500 focus:outline-none"
    }, f.options.map(opt => /*#__PURE__*/React.createElement("option", {
      key: opt,
      value: opt
    }, opt))))), /*#__PURE__*/React.createElement("div", {
      className: "col-span-2 flex flex-col gap-1"
    }, /*#__PURE__*/React.createElement("label", {
      className: "text-[10px] text-slate-400 font-mono"
    }, "[[Context]]"), /*#__PURE__*/React.createElement("input", {
      type: "text",
      value: header.context,
      onChange: e => updateHeader('context', e.target.value),
      className: "bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:border-violet-500 focus:outline-none"
    })), /*#__PURE__*/React.createElement("div", {
      className: "col-span-2 flex flex-col gap-1"
    }, /*#__PURE__*/React.createElement("label", {
      className: "text-[10px] text-slate-400 font-mono"
    }, "[[Special Instructions]]"), /*#__PURE__*/React.createElement("input", {
      type: "text",
      value: header.specialInstructions,
      onChange: e => updateHeader('specialInstructions', e.target.value),
      className: "bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 font-mono focus:border-violet-500 focus:outline-none",
      placeholder: "prov_id auto-added on mint"
    }))), /*#__PURE__*/React.createElement("div", {
      className: "mt-3 space-y-1"
    }, Object.entries(validation.fieldResults).filter(([, r]) => r.status === 'fail' || r.status === 'warn').map(([key, result]) => /*#__PURE__*/React.createElement("div", {
      key: key,
      className: "flex items-center gap-2 text-[11px]"
    }, /*#__PURE__*/React.createElement(StatusIcon, {
      status: result.status
    }), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400 font-mono"
    }, VALIDATION_RULES[key].label), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, result.msg))), validation.crossResults.filter(cr => cr.result.status === 'fail').map(cr => /*#__PURE__*/React.createElement("div", {
      key: cr.id,
      className: "flex items-center gap-2 text-[11px]"
    }, /*#__PURE__*/React.createElement(StatusIcon, {
      status: cr.result.status
    }), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400 font-mono"
    }, cr.label), /*#__PURE__*/React.createElement("span", {
      className: "text-red-300/80"
    }, cr.result.msg))))), logs.length > 0 && /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/50 backdrop-blur rounded-2xl p-4 border border-slate-700"
    }, /*#__PURE__*/React.createElement("h3", {
      className: "text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3"
    }, "Statistics"), /*#__PURE__*/React.createElement(Stats, {
      logs: logs
    })), logs.length > 0 && parentProvId && /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/50 backdrop-blur rounded-2xl p-4 border border-slate-700"
    }, /*#__PURE__*/React.createElement("h3", {
      className: "text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3"
    }, "Lineage Tree"), /*#__PURE__*/React.createElement(TreeView, {
      logs: logs,
      parentId: parentProvId
    })), !logs.length && !importedSession && /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/30 backdrop-blur rounded-2xl p-4 border border-dashed border-slate-600 text-center"
    }, /*#__PURE__*/React.createElement(Upload, {
      size: 24,
      className: "mx-auto mb-2 text-slate-500"
    }), /*#__PURE__*/React.createElement("p", {
      className: "text-xs text-slate-400"
    }, "Import a JSON to walk back through provenance:"), /*#__PURE__*/React.createElement("ul", {
      className: "text-[11px] text-slate-500 mt-2 space-y-1 text-left max-w-[220px] mx-auto"
    }, /*#__PURE__*/React.createElement("li", null, "• ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400"
    }, "read_provenance_chain output"), " — Artemis MCP chain, SHA-256 per step"), /*#__PURE__*/React.createElement("li", null, "• ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400"
    }, "agent_logs export"), " — full chain replay + walk-back"), /*#__PURE__*/React.createElement("li", null, "• ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400"
    }, "Claude session snapshot"), " — governance & scope report")))), /*#__PURE__*/React.createElement("div", {
      className: "lg:col-span-2 space-y-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/50 backdrop-blur rounded-2xl p-4 border border-slate-700"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("h3", {
      className: "text-sm font-semibold text-slate-400 uppercase tracking-wider"
    }, "🔗 Provenance Chain — 8 Steps", chainProfile === 'artemis' && /*#__PURE__*/React.createElement("span", {
      className: "ml-2 px-2 py-0.5 rounded-full text-[10px] normal-case tracking-normal bg-violet-500/20 text-violet-300 border border-violet-500/30"
    }, "Artemis MCP profile")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "w-32 h-1.5 bg-slate-700 rounded-full overflow-hidden"
    }, /*#__PURE__*/React.createElement("div", {
      className: `h-full rounded-full transition-all duration-500 ${chainScore >= 80 ? 'bg-emerald-500' : chainScore >= 40 ? 'bg-amber-500' : 'bg-slate-600'}`,
      style: {
        width: `${chainScore}%`
      }
    })), /*#__PURE__*/React.createElement("span", {
      className: "text-xs text-slate-400"
    }, completedSteps, "/", PROVENANCE_STEPS.length))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 md:grid-cols-2 gap-1.5"
    }, PROVENANCE_STEPS.map(step => {
      const state = chainState[step.id] || 'pending';
      return /*#__PURE__*/React.createElement("div", {
        key: step.id,
        className: `flex items-start gap-2 px-2.5 py-2 rounded-lg text-xs transition-all ${state === 'fail' || state === 'halt' ? 'bg-red-500/10 border border-red-500/20' : state === 'pass' ? 'bg-emerald-500/5 border border-emerald-500/10' : state === 'warn' ? 'bg-amber-500/5 border border-amber-500/10' : state === 'active' ? 'bg-cyan-500/5 border border-cyan-500/20' : 'border border-slate-700/50'}`
      }, /*#__PURE__*/React.createElement(StatusIcon, {
        status: state
      }), /*#__PURE__*/React.createElement("div", {
        className: "min-w-0"
      }, /*#__PURE__*/React.createElement("div", {
        className: "text-slate-200 font-medium"
      }, step.step, ". ", step.label), /*#__PURE__*/React.createElement("div", {
        className: "text-slate-500 text-[10px] mt-0.5 truncate"
      }, step.description), (state === 'fail' || state === 'halt') && /*#__PURE__*/React.createElement("div", {
        className: "text-red-400/80 text-[10px] mt-0.5 font-medium"
      }, step.failAction), state === 'warn' && chainProfile === 'artemis' && step.id === 'log_response' && /*#__PURE__*/React.createElement("div", {
        className: "text-amber-400/80 text-[10px] mt-0.5"
      }, "Artemis schema has no atp_response kind — last action is terminus")));
    }))), /*#__PURE__*/React.createElement("div", {
      className: "bg-slate-800/50 backdrop-blur rounded-2xl p-4 border border-slate-700"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-4"
    }, /*#__PURE__*/React.createElement("h3", {
      className: "text-sm font-semibold text-slate-400 uppercase tracking-wider"
    }, importedSession ? '📋 Session Provenance Report' : view === 'walkback' ? '⏪ Walk-Back Trail' : view === 'json' ? 'Raw Logs (JSON)' : 'Provenance Timeline'), !importedSession && logs.length > 0 && /*#__PURE__*/React.createElement("div", {
      className: "inline-flex bg-slate-900 rounded-lg p-1"
    }, ['timeline', 'walkback', 'json'].map(v => /*#__PURE__*/React.createElement("button", {
      key: v,
      onClick: () => setView(v),
      className: `px-3 py-1 rounded-md text-xs font-medium transition-all capitalize ${view === v ? 'bg-violet-500 text-white' : 'text-slate-400 hover:text-white'}`
    }, v === 'walkback' ? '⏪ walk-back' : v)))), importedSession ? /*#__PURE__*/React.createElement(SessionReport, {
      session: importedSession
    }) : logs.length === 0 ? /*#__PURE__*/React.createElement("div", {
      className: "text-center py-16 text-slate-500"
    }, /*#__PURE__*/React.createElement(GitBranch, {
      size: 48,
      className: "mx-auto mb-4 opacity-50"
    }), /*#__PURE__*/React.createElement("p", {
      className: "text-sm"
    }, "Simulate, start a live chain, or import a JSON export")) : view === 'json' ? /*#__PURE__*/React.createElement("pre", {
      className: "bg-slate-900 rounded-lg p-4 text-[10px] overflow-auto max-h-[500px] text-slate-300"
    }, JSON.stringify(logs, null, 2)) : view === 'walkback' ? /*#__PURE__*/React.createElement("div", {
      className: "space-y-2 max-h-[500px] overflow-y-auto pr-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 text-xs text-slate-500 mb-3"
    }, /*#__PURE__*/React.createElement(ArrowLeft, {
      size: 12
    }), "Walking backwards: terminus → actions (reverse-chrono) → origin. Each hop shows its parent link."), walkBackTrail.map((entry, i) => /*#__PURE__*/React.createElement("div", {
      key: entry.prov_id,
      className: "relative"
    }, i > 0 && /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1 pl-6 py-0.5 text-slate-600 text-[10px]"
    }, /*#__PURE__*/React.createElement(ArrowLeft, {
      size: 10,
      className: "rotate-90"
    }), " walked back via parent_prov_id"), /*#__PURE__*/React.createElement(LogEntry, {
      entry: entry,
      isNew: false,
      isParent: false,
      walkRole: entry.walkRole
    })))) : /*#__PURE__*/React.createElement("div", {
      className: "space-y-2 max-h-[500px] overflow-y-auto pr-2"
    }, logs.map(entry => /*#__PURE__*/React.createElement(LogEntry, {
      key: entry.prov_id,
      entry: entry,
      isNew: entry.prov_id === newLogId,
      isParent: entry.parent_prov_id === null
    })))))), /*#__PURE__*/React.createElement("div", {
      className: "text-center text-xs text-slate-500 pt-4"
    }, "Built on ", /*#__PURE__*/React.createElement("span", {
      className: "text-violet-400"
    }, "atp-provenance-logging"), " • Artemis-City Framework • Validators Toolkit v0.3 • Import • Simulate • Live • Walk-Back")));
  }
  try {
    var host = document.getElementById('root');
    ReactDOM.createRoot(host).render(React.createElement(ATPMissionControl));
    document.getElementById('fallback').style.display = 'none';
  } catch (err) {
    var box = document.getElementById('fallback');
    box.setAttribute('data-reason', 'render-threw');
    box.querySelector('#fallback-detail').textContent = err && err.stack || String(err);
  }
})();
