import { describe, test } from 'bun:test';

const generatedDir = `${import.meta.dir}/../generated_ts`;
const fixturesDir = `${generatedDir}/fixtures`;
const nodeModulesDir = `${import.meta.dir}/node_modules`;

const glob = new Bun.Glob('*.{mts,cts,tsx,ts,mjs,cjs,jsx,js}');
const snippetFiles = (await Array.fromAsync(glob.scan({ cwd: generatedDir }))).sort();

async function runSnippet(file: string) {
  const childEnv: Record<string, string> = {
    NODE_PATH: nodeModulesDir,
    PATH: process.env.PATH ?? '',
    HOME: process.env.HOME ?? '',
  };
  for (const key of [
    'EDEN_AI_SANDBOX_API_TOKEN',
    'EDEN_AI_BASE_URL',
    '_EDEN_TEST_FILE_ID',
  ]) {
    const value = process.env[key];
    if (value) childEnv[key] = value;
  }

  const proc = Bun.spawn(['bun', 'run', `${generatedDir}/${file}`], {
    cwd: fixturesDir,
    env: childEnv,
    stdout: 'pipe',
    stderr: 'pipe',
  });
  await proc.exited;
  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();
  return { exitCode: proc.exitCode ?? -1, stdout, stderr };
}

describe('typescript documentation snippets', () => {
  if (!process.env.EDEN_AI_SANDBOX_API_TOKEN) {
    test.skip('EDEN_AI_SANDBOX_API_TOKEN not set', () => {});
    return;
  }

  for (const file of snippetFiles) {
    if (file.includes('.skip.')) {
      test.skip(file, () => {});
      continue;
    }

    test(
      file,
      async () => {
        const { exitCode, stdout, stderr } = await runSnippet(file);
        if (exitCode !== 0) {
          throw new Error(
            `snippet: ${file}\n` +
              `expected: exit code 0\n` +
              `actual:   exit code ${exitCode}\n` +
              `--- stdout ---\n${stdout || '(empty)'}\n` +
              `--- stderr ---\n${stderr || '(empty)'}`,
          );
        }
      },
      30_000,
    );
  }
});
