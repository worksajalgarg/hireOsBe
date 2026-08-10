import { MiddlewareConsumer, Module, NestModule } from "@nestjs/common";
import { APP_GUARD } from "@nestjs/core";
import { ScheduleModule } from "@nestjs/schedule";
import { ThrottlerGuard, ThrottlerModule } from "@nestjs/throttler";
import { CommonModule } from "./common/common.module";
import { TenantContextMiddleware } from "./common/tenant-context.middleware";
import { RolesGuard } from "./common/roles.guard";
import { TenantModule } from "./tenant/tenant.module";
import { UsersModule } from "./users/users.module";
import { AuditModule } from "./audit/audit.module";
import { JobRolesModule } from "./job-roles/job-roles.module";
import { ResumesModule } from "./resumes/resumes.module";
import { CandidatesModule } from "./candidates/candidates.module";
import { WorkflowModule } from "./workflow/workflow.module";
import { IntegrationsModule } from "./integrations/integrations.module";
import { InterviewsModule } from "./interviews/interviews.module";
import { AuthModule } from "./auth/auth.module";
import { JwtAuthGuard } from "./auth/jwt-auth.guard";
import { PermissionsGuard } from "./auth/permissions.guard";
import { WorkspaceModule } from "./workspace/workspace.module";
import { RbacModule } from "./rbac/rbac.module";

import { PromptsModule } from "./prompts/prompts.module";

@Module({
  imports: [
    ThrottlerModule.forRoot([{ ttl: 60_000, limit: 100 }]),
    ScheduleModule.forRoot(),
    CommonModule,
    AuthModule,
    TenantModule,
    UsersModule,
    WorkspaceModule,
    RbacModule,
    AuditModule,
    JobRolesModule,
    ResumesModule,
    CandidatesModule,
    WorkflowModule,
    IntegrationsModule,
    InterviewsModule,
    PromptsModule,
  ],
  providers: [
    { provide: APP_GUARD, useClass: ThrottlerGuard },
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: PermissionsGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(TenantContextMiddleware).forRoutes("{*path}");
  }
}
