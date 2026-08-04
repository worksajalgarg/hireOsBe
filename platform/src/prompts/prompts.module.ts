import { Module } from "@nestjs/common";
import { PromptsController } from "./prompts.controller";
import { PromptsService } from "./prompts.service";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";

@Module({
  controllers: [PromptsController],
  providers: [PromptsService, PrismaService, AuditService],
  exports: [PromptsService],
})
export class PromptsModule {}
