/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** base da API (default /api, servida pelo proxy do Vite ou pelo proprio backend) */
  readonly VITE_API_BASE?: string;
}
