import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
const args=process.argv.slice(2);
const get=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const bundled='/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const python=existsSync(bundled)?bundled:(process.env.CODEX_PRIMARY_RUNTIME_PYTHON||'python3');
const child=spawn(python,['-m','uvicorn','app.main:app','--host',get('--host','0.0.0.0'),'--port',get('--port',process.env.PORT||'3000')],{stdio:'inherit',env:process.env});
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill(signal));
child.on('exit',code=>process.exit(code??1));
