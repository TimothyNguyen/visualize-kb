import { describe, expect, it } from 'vitest'

import { devProxy } from './vite.proxy.ts'

describe('Vite development proxy', () => {
  it('routes CopilotKit separately and every other API endpoint to the Python backend', () => {
    expect(Object.entries(devProxy)).toEqual([
      ['/api/copilotkit', 'http://127.0.0.1:3001'],
      ['/api', 'http://127.0.0.1:8420'],
    ])
  })
})
