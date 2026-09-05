const path = require("path");

module.exports = {
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
