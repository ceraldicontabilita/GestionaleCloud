const path = require("path");

module.exports = {
  jest: {
    configure: config => {
      config.moduleNameMapper = { ...config.moduleNameMapper, '^@/(.*)$': '<rootDir>/src/$1' };
      // Jest 27 non risolve gli exports condizionali delle versioni Radix recenti.
      try {
        config.moduleNameMapper['^@radix-ui/primitive/is-development$'] = require.resolve('@radix-ui/primitive/is-development');
      } catch (_) { /* Le versioni precedenti non importano questo sottopercorso. */ }
      return config;
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (config) => {
      const scope = config.resolve.plugins.find(p => p.constructor.name === 'ModuleScopePlugin');
      if (scope) scope.allowedPaths.push(path.resolve(__dirname, '../frontend_shared'));
      return config;
    },
  },
};
