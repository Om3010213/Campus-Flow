import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir:'./e2e', fullyParallel:false, workers:1, timeout:60000,
  use:{baseURL:'http://127.0.0.1:5174',channel:'chrome',headless:true,viewport:{width:1440,height:1000},screenshot:'only-on-failure'},
  webServer:[
    {command:process.platform==='win32'?'../.venv/Scripts/python.exe ../scripts/e2e_backend.py':'../.venv/bin/python ../scripts/e2e_backend.py',url:'http://127.0.0.1:8001/api/health',timeout:30000},
    {command:'pnpm exec vite --host 127.0.0.1 --port 5174 --strictPort',url:'http://127.0.0.1:5174',env:{CAMPUSFLOW_API_TARGET:'http://127.0.0.1:8001'},timeout:30000},
  ],
})
