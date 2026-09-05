import { zodToJsonSchema } from "zod-to-json-schema";
import type { z } from "zod";

/**
 * Converts a Zod schema into an OpenAPI 3-compatible JSON schema for Fastify Swagger.
 */
export function toJsonSchema(zodSchema: z.ZodTypeAny) {
  const schema = zodToJsonSchema(zodSchema, { target: "jsonSchema7" }) as Record<string, any>;
  // Remove $schema property to prevent Fastify JSON schema validator warnings
  const { $schema, ...clean } = schema;
  return clean;
}
