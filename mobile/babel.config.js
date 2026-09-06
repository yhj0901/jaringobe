// Expo 기본 Babel 설정 (jest-expo 프리셋 공용)
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
  };
};
