import { Module } from "@nestjs/common";
import { WorkspaceController } from "./workspace.controller";
import { TenantModule } from "../tenant/tenant.module";
import { UsersModule } from "../users/users.module";

@Module({
  imports: [TenantModule, UsersModule],
  controllers: [WorkspaceController],
})
export class WorkspaceModule {}
