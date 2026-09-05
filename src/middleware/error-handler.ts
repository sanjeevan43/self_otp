import type { FastifyError, FastifyReply, FastifyRequest } from "fastify";
import { AppError } from "../common/errors/app-error.js";
import { logger } from "../plugins/logger.js";
import { ZodError } from "zod";

export function errorHandler(error: FastifyError | Error, request: FastifyRequest, reply: FastifyReply) {
  const reqId = request.id;

  if (error instanceof AppError) {
    if (error.code) {
      return reply.status(error.statusCode).send({
        detail: {
          code: error.code,
          message: error.message,
          ...(error.details ? { details: error.details } : {}),
        },
      });
    }
    return reply.status(error.statusCode).send({
      detail: error.message,
    });
  }

  if (error instanceof ZodError) {
    return reply.status(422).send({
      detail: error.issues.map((issue) => ({
        loc: ["body", ...issue.path],
        msg: issue.message,
        type: issue.code,
      })),
    });
  }

  // Fastify native schema validation error
  if ("validation" in error && error.validation) {
    return reply.status(422).send({
      detail: error.validation,
    });
  }

  // JWT errors
  if ("statusCode" in error && error.statusCode === 401) {
    return reply.status(401).send({
      detail: {
        code: "UNAUTHORIZED",
        message: error.message || "Could not validate credentials.",
      },
    });
  }

  logger.error({ err: error, reqId }, "Unhandled application exception");

  return reply.status(500).send({
    detail: "Internal server error",
  });
}
