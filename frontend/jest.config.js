/** @type {import('jest').Config} */
const config = {
  testEnvironment: "jsdom",
  transform: {
    "^.+\\.(t|j)sx?$": ["babel-jest", { configFile: "./babel.config.jest.js" }],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testMatch: ["<rootDir>/tests/unit/**/*.test.{ts,tsx}"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx"],
};

module.exports = config;
