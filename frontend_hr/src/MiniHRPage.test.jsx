// @vitest-environment node
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, test} from 'vitest';
import MiniHRPage from './MiniHRPage';

test('MiniHR does not load browser-only custom elements during HR SSR imports',()=>{
  expect(typeof HTMLElement).toBe('undefined');
  expect(renderToStaticMarkup(<MiniHRPage/>)).toContain('Fascicolo mensile');
});
