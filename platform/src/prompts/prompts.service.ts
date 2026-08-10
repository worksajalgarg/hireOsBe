import { Injectable, NotFoundException, OnModuleInit } from "@nestjs/common";
import { randomUUID } from "crypto";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { CreatePromptTemplateDto, UpdatePromptTemplateDto } from "./dto";

export interface PromptRecord {
  id: string;
  tenantId: string;
  title: string;
  description?: string | null;
  category: string;
  conversationFlow?: string | null;
  openingInstructions?: string | null;
  silenceInstructions?: string | null;
  systemBoundaries?: string | null;
  isDefault: boolean;
  createdAt: Date;
  updatedAt: Date;
}

interface PromptTemplateDelegate {
  findMany(args: {
    where: { tenantId: string };
    orderBy: { createdAt: string };
  }): Promise<PromptRecord[]>;
  findFirst(args: { where: { id: string; tenantId: string } }): Promise<PromptRecord | null>;
  create(args: { data: Record<string, unknown> }): Promise<PromptRecord>;
  update(args: { where: { id: string }; data: Record<string, unknown> }): Promise<PromptRecord>;
  delete(args: { where: { id: string } }): Promise<PromptRecord>;
}

@Injectable()
export class PromptsService implements OnModuleInit {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  async onModuleInit() {
    try {
      await this.prisma.$executeRawUnsafe(`
        CREATE TABLE IF NOT EXISTS prompt_templates (
          id VARCHAR(36) PRIMARY KEY,
          tenant_id VARCHAR(36) NOT NULL,
          title VARCHAR(255) NOT NULL,
          description TEXT,
          category VARCHAR(50) DEFAULT 'Technical',
          conversation_flow TEXT,
          opening_instructions TEXT,
          silence_instructions TEXT,
          system_boundaries TEXT,
          is_default BOOLEAN DEFAULT false,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
      `);
    } catch {
      // Table already exists or initialized by prisma migration
    }
  }

  private get delegate(): PromptTemplateDelegate | undefined {
    return (this.prisma as unknown as { promptTemplate?: PromptTemplateDelegate }).promptTemplate;
  }

  async listForTenant(tenantId: string): Promise<PromptRecord[]> {
    if (this.delegate) {
      return this.delegate.findMany({
        where: { tenantId },
        orderBy: { createdAt: "desc" },
      });
    }
    // Fallback raw-SQL path, kept in the same shape as getById/create/etc.
    // Fixed two real bugs surfaced by prompt_templates.tenant_id becoming a
    // proper UUID column: comparing it to the literal string 'system'
    // crashed outright (invalid uuid syntax), and the trailing `OR true`
    // made the whole WHERE clause always match — every tenant was seeing
    // every other tenant's prompt templates.
    const rows = await this.prisma.$queryRaw<PromptRecord[]>`
      SELECT id, tenant_id as "tenantId", title, description, category,
             conversation_flow as "conversationFlow",
             opening_instructions as "openingInstructions",
             silence_instructions as "silenceInstructions",
             system_boundaries as "systemBoundaries",
             is_default as "isDefault",
             created_at as "createdAt", updated_at as "updatedAt"
      FROM prompt_templates
      WHERE tenant_id = ${tenantId} OR is_default = true
      ORDER BY created_at DESC
    `;
    return rows as PromptRecord[];
  }

  async getById(tenantId: string, id: string): Promise<PromptRecord> {
    if (this.delegate) {
      const prompt = await this.delegate.findFirst({
        where: { id, tenantId },
      });
      if (!prompt) throw new NotFoundException("Prompt template not found");
      return prompt;
    }
    const rows = await this.prisma.$queryRaw<PromptRecord[]>`
      SELECT id, tenant_id as "tenantId", title, description, category,
             conversation_flow as "conversationFlow",
             opening_instructions as "openingInstructions",
             silence_instructions as "silenceInstructions",
             system_boundaries as "systemBoundaries",
             is_default as "isDefault",
             created_at as "createdAt", updated_at as "updatedAt"
      FROM prompt_templates
      WHERE id = ${id} AND tenant_id = ${tenantId}
      LIMIT 1
    `;
    if (!rows.length) throw new NotFoundException("Prompt template not found");
    return rows[0] as PromptRecord;
  }

  async create(tenantId: string, actorId: string, dto: CreatePromptTemplateDto): Promise<PromptRecord> {
    let prompt: PromptRecord;
    if (this.delegate) {
      prompt = await this.delegate.create({
        data: {
          tenantId,
          title: dto.title,
          description: dto.description,
          category: dto.category ?? "Technical",
          conversationFlow: dto.conversationFlow,
          openingInstructions: dto.openingInstructions,
          silenceInstructions: dto.silenceInstructions,
          systemBoundaries: dto.systemBoundaries,
          isDefault: dto.isDefault ?? false,
        },
      });
    } else {
      const id = randomUUID();
      const rows = await this.prisma.$queryRaw<PromptRecord[]>`
        INSERT INTO prompt_templates (id, tenant_id, title, description, category, conversation_flow, opening_instructions, silence_instructions, system_boundaries, is_default, created_at, updated_at)
        VALUES (${id}, ${tenantId}, ${dto.title}, ${dto.description ?? null}, ${dto.category ?? "Technical"}, ${dto.conversationFlow ?? null}, ${dto.openingInstructions ?? null}, ${dto.silenceInstructions ?? null}, ${dto.systemBoundaries ?? null}, ${dto.isDefault ?? false}, NOW(), NOW())
        RETURNING id, tenant_id as "tenantId", title, description, category, conversation_flow as "conversationFlow", opening_instructions as "openingInstructions", silence_instructions as "silenceInstructions", system_boundaries as "systemBoundaries", is_default as "isDefault", created_at as "createdAt", updated_at as "updatedAt"
      `;
      prompt = rows[0] as PromptRecord;
    }

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "prompt.template.created",
      entityType: "prompt_template",
      entityId: prompt.id,
      payload: { title: prompt.title, category: prompt.category },
    });

    return prompt;
  }

  async update(
    tenantId: string,
    actorId: string,
    id: string,
    dto: UpdatePromptTemplateDto,
  ): Promise<PromptRecord> {
    await this.getById(tenantId, id);
    let updated: PromptRecord;

    if (this.delegate) {
      updated = await this.delegate.update({
        where: { id },
        data: {
          title: dto.title,
          description: dto.description,
          category: dto.category,
          conversationFlow: dto.conversationFlow,
          openingInstructions: dto.openingInstructions,
          silenceInstructions: dto.silenceInstructions,
          systemBoundaries: dto.systemBoundaries,
          isDefault: dto.isDefault,
        },
      });
    } else {
      const rows = await this.prisma.$queryRaw<PromptRecord[]>`
        UPDATE prompt_templates
        SET title = COALESCE(${dto.title ?? null}, title),
            description = COALESCE(${dto.description ?? null}, description),
            category = COALESCE(${dto.category ?? null}, category),
            conversation_flow = COALESCE(${dto.conversationFlow ?? null}, conversation_flow),
            opening_instructions = COALESCE(${dto.openingInstructions ?? null}, opening_instructions),
            silence_instructions = COALESCE(${dto.silenceInstructions ?? null}, silence_instructions),
            system_boundaries = COALESCE(${dto.systemBoundaries ?? null}, system_boundaries),
            updated_at = NOW()
        WHERE id = ${id}
        RETURNING id, tenant_id as "tenantId", title, description, category, conversation_flow as "conversationFlow", opening_instructions as "openingInstructions", silence_instructions as "silenceInstructions", system_boundaries as "systemBoundaries", is_default as "isDefault", created_at as "createdAt", updated_at as "updatedAt"
      `;
      updated = rows[0] as PromptRecord;
    }

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "prompt.template.updated",
      entityType: "prompt_template",
      entityId: updated.id,
      payload: { title: updated.title },
    });

    return updated;
  }

  async delete(tenantId: string, actorId: string, id: string): Promise<{ deleted: boolean }> {
    const prompt = await this.getById(tenantId, id);

    if (this.delegate) {
      await this.delegate.delete({ where: { id } });
    } else {
      await this.prisma.$executeRaw`DELETE FROM prompt_templates WHERE id = ${id}`;
    }

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "prompt.template.deleted",
      entityType: "prompt_template",
      entityId: id,
      payload: { title: prompt.title },
    });

    return { deleted: true };
  }
}
