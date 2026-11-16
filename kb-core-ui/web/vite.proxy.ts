export const devProxy = {
  '/api/copilotkit': process.env.VITE_COPILOTKIT_PROXY ?? 'http://127.0.0.1:3001',
  '/api': process.env.VITE_KB_CORE_UI_PROXY ?? 'http://127.0.0.1:8420',
}
