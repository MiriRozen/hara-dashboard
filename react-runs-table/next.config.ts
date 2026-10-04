import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the JSON fixtures live one level up, in the repo's shared data/ folder
  outputFileTracingRoot: path.join(import.meta.dirname, ".."),
};

export default nextConfig;
