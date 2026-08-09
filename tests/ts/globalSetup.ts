const repoRoot = `${import.meta.dir}/../..`;
const envFile = Bun.file(`${repoRoot}/tests/.env`);

if (await envFile.exists()) {
  for (const line of (await envFile.text()).split('\n')) {
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    if (!key || key.startsWith('#')) continue;
    const value = line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '');
    process.env[key] ??= value;
  }
}

const venvPython = `${repoRoot}/.venv/bin/python`;
const python = (await Bun.file(venvPython).exists())
  ? venvPython
  : Bun.which('python3') ?? Bun.which('python');

if (!python) throw new Error('No Python interpreter found');

const result = Bun.spawnSync([python, '-m', 'tests.snippet_extractor'], {
  cwd: repoRoot,
  stdout: 'inherit',
  stderr: 'inherit',
});

if (!result.success) {
  throw new Error(`Snippet extraction failed (exit code ${result.exitCode})`);
}
