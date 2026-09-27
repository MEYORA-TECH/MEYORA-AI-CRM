/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the API lives when it has its own domain, e.g. https://api.meyora.in. Empty: same origin (/api). */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
