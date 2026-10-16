import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode})=>{const env=loadEnv(mode,'.','GLUCOTWIN_');return {plugins:[react()],server:{host:'127.0.0.1',port:Number(env.GLUCOTWIN_WEB_PORT??15173),strictPort:true,proxy:{'/api':`http://127.0.0.1:${env.GLUCOTWIN_API_PORT??18060}`}}}});
