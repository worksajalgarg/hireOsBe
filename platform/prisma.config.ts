import path from "node:path";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: path.join("prisma", "schema.prisma"),
  datasource: {
    url: process.env.DATABASE_URL || "postgresql://placeholder:placeholder@localhost:5432/placeholder",
    // Only needed for `prisma migrate dev`/`migrate diff` against a migrations
    // directory (Prisma computes the expected schema here before diffing).
    // Not read at runtime by the app itself.
    shadowDatabaseUrl: process.env.SHADOW_DATABASE_URL,
  },
});
