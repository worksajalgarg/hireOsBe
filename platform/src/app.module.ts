import { MiddlewareConsumer, Module, NestModule } from "@nestjs/common";
import { APP_GUARD } from "@nestjs/core";
import { CommonModule } from "./common/common.module";
import { TenantContextMiddleware } from "./common/tenant-context.middleware";
import { RolesGuard } from "./common/roles.guard";
import { TenantModule } from "./tenant/tenant.module";
import { UsersModule } from "./users/users.module";
import { AuditModule } from "./audit/audit.module";
import { RoleContextModule } from "./role-context/role-context.module";
import { CandidatesModule } from "./candidates/candidates.module";
import { WorkflowModule } from "./workflow/workflow.module";
import { IntegrationsModule } from "./integrations/integrations.module";

@Module({
  imports: [
    CommonModule,
    TenantModule,
    UsersModule,
    AuditModule,
    RoleContextModule,
    CandidatesModule,
    WorkflowModule,
    IntegrationsModule,
  ],
  providers: [{ provide: APP_GUARD, useClass: RolesGuard }],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(TenantContextMiddleware).forRoutes("*");
  }
}
