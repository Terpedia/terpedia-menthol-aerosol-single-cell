import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { readFile, mkdir, writeFile, realpath } from 'node:fs/promises';
import { resolve, relative, sep, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('.', import.meta.url)));
const classes = new Set(['observed', 'source-reported', 'proposed']);
const sections = ['background', 'methods', 'results', 'interpretation', 'limitations', 'next_steps'];

function workspacePathFor(workspaceRoot, value, allowed) {
  const path = resolve(workspaceRoot, String(value || ''));
  const name = relative(workspaceRoot, path);
  if (!name || name.startsWith('..') || name.includes(`..${sep}`) || !allowed.some((prefix) => name.startsWith(`${prefix}${sep}`))) {
    throw new Error(`Path must remain under ${allowed.join(' or ')}: ${value}`);
  }
  return { path, name };
}

function sha256(content) { return createHash('sha256').update(content).digest('hex'); }
async function sha256File(path) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest('hex');
}
function text(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} is required`);
  return value.trim();
}
function publicUrl(value) {
  const url = new URL(text(value, 'Source URL'));
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error(`Source URL must use HTTP(S): ${value}`);
  return url.toString();
}
export async function generateResearchReport(manifestPath, workspaceRoot = root) {
  const workspacePath = (value, allowed) => workspacePathFor(workspaceRoot, value, allowed);
  const manifestFile = workspacePath(manifestPath, ['research']);
  const manifestBytes = await readFile(manifestFile.path);
  const spec = JSON.parse(manifestBytes.toString('utf8'));
  if (![1, 2].includes(spec.schema_version)) throw new Error('Report specification requires schema_version 1 or 2');
  const title = text(spec.title, 'Title');
  const question = text(spec.question, 'Research question');
  const slug = text(spec.slug, 'Slug');
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(slug)) throw new Error('Slug must be lowercase letters, digits, and hyphens');
  const notebookFile = workspacePath(spec.notebook, ['notebooks']);
  if (!notebookFile.name.endsWith('.ipynb')) throw new Error('Notebook must be an .ipynb file');
  const notebookBytes = await readFile(notebookFile.path);
  const notebook = JSON.parse(notebookBytes.toString('utf8'));
  if (notebook.nbformat !== 4 || !Array.isArray(notebook.cells)) throw new Error('Notebook is not nbformat 4');
  const codeCells = notebook.cells.filter((cell) => cell.cell_type === 'code');
  const executedCells = codeCells.filter((cell) => Number.isInteger(cell.execution_count) && cell.execution_count > 0).length;
  if (codeCells.some((cell) => cell.outputs?.some((output) => output.output_type === 'error'))) throw new Error('Notebook contains an error output');
  if (codeCells.length && executedCells !== codeCells.length) throw new Error('Every notebook code cell must have an execution count');
  let executionReceipt = null;
  let executionReceiptFile = null;
  let executionReceiptBytes = null;
  const inputHashes = new Map();
  if (spec.schema_version === 2) {
    executionReceiptFile = workspacePath(spec.execution_receipt, ['research']);
    executionReceiptBytes = await readFile(executionReceiptFile.path);
    executionReceipt = JSON.parse(executionReceiptBytes.toString('utf8'));
    if (executionReceipt.schema_version !== 2 || executionReceipt.runner !== 'terputer-notebook-runner-v1'
        || executionReceipt.notebook !== notebookFile.name || executionReceipt.notebook_sha256 !== sha256(notebookBytes)
        || executionReceipt.executed_code_cells !== executedCells) {
      throw new Error('Notebook execution receipt does not match this executed notebook');
    }
    const pinned = executionReceipt.inputs_pinned ?? {};
    if (typeof pinned !== 'object' || Array.isArray(pinned) || Object.keys(pinned).length > 50) {
      throw new Error('Notebook execution receipt has invalid pinned inputs');
    }
    const realRoot = await realpath(workspaceRoot);
    for (const [name, expectedHash] of Object.entries(pinned)) {
      const input = workspacePath(name, ['research', 'terputer_bio']);
      const realInput = await realpath(input.path);
      if (!['research', 'terputer_bio'].some((prefix) => relative(realRoot, realInput).startsWith(`${prefix}${sep}`))) {
        throw new Error(`Pinned input leaves the research workspace: ${input.name}`);
      }
      if (!/^[a-f0-9]{64}$/.test(String(expectedHash)) || await sha256File(input.path) !== expectedHash) {
        throw new Error(`Pinned input changed since notebook execution: ${input.name}`);
      }
      inputHashes.set(input.name, expectedHash);
    }
  }

  if (!Array.isArray(spec.sources) || !spec.sources.length) throw new Error('At least one source is required');
  const dataInputs = [];
  if (spec.data_inputs !== undefined) {
    if (spec.schema_version !== 2 || !Array.isArray(spec.data_inputs) || spec.data_inputs.length > 50) {
      throw new Error('Data inputs require a version 2 report and an array of at most 50 entries');
    }
    const seen = new Set();
    for (const entry of spec.data_inputs) {
      const input = workspacePath(text(entry.path, 'Data input path'), ['research']);
      if (seen.has(input.name)) throw new Error(`Duplicate data input: ${input.name}`);
      seen.add(input.name);
      const expectedHash = text(entry.sha256, `Data input ${input.name} SHA-256`);
      if (!/^[a-f0-9]{64}$/.test(expectedHash) || inputHashes.get(input.name) !== expectedHash) {
        throw new Error(`Data input does not match the notebook execution receipt: ${input.name}`);
      }
      const url = publicUrl(entry.url);
      const parsedUrl = new URL(url);
      if (parsedUrl.protocol !== 'https:' || parsedUrl.username || parsedUrl.password) {
        throw new Error(`Data input requires an HTTPS download URL without credentials: ${input.name}`);
      }
      dataInputs.push({ path: input.name, url, sha256: expectedHash });
    }
  }
  const sources = new Map();
  for (const source of spec.sources) {
    const id = text(source.id, 'Source ID');
    if (sources.has(id)) throw new Error(`Duplicate source ID: ${id}`);
    sources.set(id, { title: text(source.title, `Source ${id} title`), url: publicUrl(source.url) });
  }
  if (!Array.isArray(spec.claims) || !spec.claims.length) throw new Error('At least one claim is required');
  const claims = new Map();
  const artifacts = new Map();
  for (const claim of spec.claims) {
    const id = text(claim.id, 'Claim ID');
    if (claims.has(id)) throw new Error(`Duplicate claim ID: ${id}`);
    if (!classes.has(claim.class)) throw new Error(`Invalid evidence class for ${id}`);
    const claimText = text(claim.text, `Claim ${id} text`);
    const limitation = text(claim.limitation, `Claim ${id} limitation`);
    const sourceIds = Array.isArray(claim.sources) ? claim.sources : [];
    if (!sourceIds.length || sourceIds.some((sourceId) => !sources.has(sourceId))) throw new Error(`Claim ${id} needs valid source IDs`);
    const paths = Array.isArray(claim.artifacts) ? claim.artifacts : [];
    if (claim.class === 'observed' && (!paths.length || !executedCells)) {
      throw new Error(`Observed claim ${id} requires a result artifact and an executed notebook`);
    }
    for (const value of paths) {
      const artifact = workspacePath(value, ['research']);
      const bytes = await readFile(artifact.path);
      const artifactHash = sha256(bytes);
      if (claim.class === 'observed' && executionReceipt && executionReceipt.artifacts_written?.[artifact.name] !== artifactHash) {
        throw new Error(`Observed claim ${id} references an artifact not recorded by the notebook run: ${artifact.name}`);
      }
      artifacts.set(artifact.name, artifactHash);
    }
    claims.set(id, { ...claim, text: claimText, limitation, sources: sourceIds, artifacts: paths });
  }
  if (!spec.sections || typeof spec.sections !== 'object') throw new Error('Report sections are required');
  for (const section of sections) {
    if (!Array.isArray(spec.sections[section]) || !spec.sections[section].length) throw new Error(`Section ${section} needs claim IDs`);
    for (const id of spec.sections[section]) if (!claims.has(id)) throw new Error(`Section ${section} references missing claim ${id}`);
  }
  const unused = [...claims.keys()].filter((id) => !sections.some((section) => spec.sections[section].includes(id)));
  if (unused.length) throw new Error(`Claims not used in report: ${unused.join(', ')}`);
  if (!Array.isArray(spec.abstract) || !spec.abstract.length || spec.abstract.some((id) => !claims.has(id))) {
    throw new Error('Abstract must list valid claim IDs in the intended order');
  }
  const sourceNumbers = new Map([...sources.keys()].map((id, index) => [id, index + 1]));
  const outputDir = join(workspaceRoot, 'research', slug, 'generated');
  const claimLine = (id, includeArtifacts = true, includeLimitation = false) => {
    const claim = claims.get(id);
    const refs = claim.sources.map((sourceId) => `[${sourceNumbers.get(sourceId)}](${sources.get(sourceId).url})`).join(', ');
    const artifactLinks = includeArtifacts ? claim.artifacts.map((value) => {
      const file = workspacePath(value, ['research']);
      return `[${file.name}](${relative(outputDir, file.path).split(sep).join('/')})`;
    }) : [];
    const prefix = {
      observed: '**Observed in notebook:** ',
      'source-reported': '**Source-reported:** ',
      proposed: '**Proposed:** ',
    }[claim.class];
    return `${prefix}${claim.text} (claim ${id}; ${refs})${artifactLinks.length ? ` Artifacts: ${artifactLinks.join(', ')}.` : ''}${includeLimitation ? ` **Limitation:** ${claim.limitation}` : ''}`;
  };
  const limitationLine = (id) => {
    const claim = claims.get(id);
    const refs = claim.sources.map((sourceId) => `[${sourceNumbers.get(sourceId)}](${sources.get(sourceId).url})`).join(', ');
    return `**Claim ${id} (${claim.class}):** ${claim.text} **Limitation:** ${claim.limitation} (${refs})`;
  };
  const headings = { background: 'Background', methods: 'Methods', results: 'Results', interpretation: 'Interpretation', limitations: 'Limitations', next_steps: 'Next research steps' };
  const lines = [
    `# ${title}`, '',
    '> Generated evidence brief. Each statement is linked to a claim record; scientific interpretation still requires review.', '',
    `**Research question:** ${question}`, '',
    `**Notebook:** \`${notebookFile.name}\` · SHA-256 \`${sha256(notebookBytes)}\` · ${executedCells} executed code cells`, '',
    '## Abstract', '',
    ...spec.abstract.flatMap((id) => [claimLine(id, false), '']),
  ];
  for (const section of sections) {
    lines.push(`## ${headings[section]}`, '');
    for (const id of spec.sections[section]) {
      lines.push(section === 'limitations' ? limitationLine(id) : claimLine(id, true, section === 'results' || section === 'interpretation'), '');
    }
  }
  lines.push('## Data and code availability', '', `The source specification is \`${manifestFile.name}\` (SHA-256 \`${sha256(manifestBytes)}\`). The claim ledger and generation receipt accompany this report. File hashes identify the report files and cited result artifacts.${dataInputs.length ? ` ${dataInputs.length} externally sourced input file${dataInputs.length === 1 ? '' : 's'} ${dataInputs.length === 1 ? 'has' : 'have'} a source URL and hash listed below.` : ' External data inputs require their own pinned URLs and checksums.'}${executionReceiptFile ? ` The [notebook execution receipt](${relative(outputDir, executionReceiptFile.path).split(sep).join('/')}) matches the saved notebook and records hashes for result files written during its fresh-kernel run.${inputHashes.size ? ` It also pins ${inputHashes.size} declared local input file${inputHashes.size === 1 ? '' : 's'} by SHA-256.` : ' No local input files were declared for this run.'}${executionReceipt.environment?.package_versions ? ' It records the Python version and installed package versions.' : ' This older receipt does not record installed-package versions.'}` : ''} Notebook execution does not independently validate scientific interpretation.`, '');
  if (dataInputs.length) {
    lines.push('### External data files', '', 'The following download locations and file hashes match inputs pinned by the notebook execution receipt. The generator does not download these files or verify that the URLs remain live.', '', '| Input | Download | SHA-256 |', '| --- | --- | --- |', ...dataInputs.map((item) => `| \`${item.path}\` | [Source file](${item.url}) | \`${item.sha256}\` |`), '');
  }
  lines.push('## References', '');
  for (const [id, source] of sources) lines.push(`[${sourceNumbers.get(id)}] ${source.title}. ${source.url}`);
  lines.push('');
  const ledger = ['claim_id\tevidence_class\tclaim\tsource_ids\tsource_urls\tartifacts\tlimitation'];
  for (const [id, claim] of claims) ledger.push([id, claim.class, claim.text, claim.sources.join(';'), claim.sources.map((sourceId) => sources.get(sourceId).url).join(';'), claim.artifacts.join(';'), claim.limitation].map((value) => String(value).replaceAll('\t', ' ').replaceAll('\n', ' ')).join('\t'));
  await mkdir(outputDir, { recursive: true });
  const report = lines.join('\n');
  const ledgerText = `${ledger.join('\n')}\n`;
  const receipt = {
    schema_version: 1, generator: 'terputer-report-generator-v2', specification_schema_version: spec.schema_version,
    manifest: manifestFile.name, manifest_sha256: sha256(manifestBytes),
    notebook: notebookFile.name, notebook_sha256: sha256(notebookBytes), executed_code_cells: executedCells,
    ...(executionReceiptFile ? { notebook_execution_receipt: executionReceiptFile.name, notebook_execution_receipt_sha256: sha256(executionReceiptBytes) } : {}),
    artifact_sha256: Object.fromEntries([...artifacts].sort(([a], [b]) => a.localeCompare(b))),
    ...(inputHashes.size ? { input_sha256: Object.fromEntries([...inputHashes].sort(([a], [b]) => a.localeCompare(b))) } : {}),
    ...(dataInputs.length ? { external_data_inputs: dataInputs } : {}),
    claim_count: claims.size, observed_claim_count: [...claims.values()].filter((claim) => claim.class === 'observed').length,
    report_sha256: sha256(report), ledger_sha256: sha256(ledgerText),
    limits: 'Checks source URL syntax, local artifact presence, notebook execution metadata, and provenance; version 2 specifications also bind a recorded run to the notebook, observed-claim artifact hashes, and any declared local input hashes. Does not verify that a notebook read every declared input, live URL reachability, biological replication, or claim truth.'
  };
  await writeFile(join(outputDir, 'white-paper.md'), report);
  await writeFile(join(outputDir, 'claim-ledger.tsv'), ledgerText);
  await writeFile(join(outputDir, 'generation-receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`);
  return { directory: `research/${slug}/generated`, report: `research/${slug}/generated/white-paper.md`, ledger: `research/${slug}/generated/claim-ledger.tsv`, receipt: `research/${slug}/generated/generation-receipt.json`, ...receipt };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const manifest = process.argv[2];
  if (!manifest) { console.error('Usage: node report-generator.mjs research/<project>/report-spec.json'); process.exitCode = 2; }
  else generateResearchReport(manifest).then((result) => console.log(JSON.stringify(result, null, 2))).catch((error) => { console.error(error.message); process.exitCode = 1; });
}
