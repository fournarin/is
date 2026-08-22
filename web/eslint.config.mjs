// Flat config, which is the only kind eslint 9 reads and the only kind
// `eslint-config-next` 16 ships. `next lint` no longer exists, so CI and a
// developer both run the same `eslint .` from here.
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  { ignores: [".next/**", "next-env.d.ts"] },
  ...coreWebVitals,
  ...typescript,
];

export default config;
