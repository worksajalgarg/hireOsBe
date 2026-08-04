import { Module } from "@nestjs/common";
import { JwtModule } from "@nestjs/jwt";
import { AuthController } from "./auth.controller";
import { AuthService } from "./auth.service";
import { JwtAuthGuard } from "./jwt-auth.guard";
import { PermissionsGuard } from "./permissions.guard";
import { TenantAccessGuard } from "./tenant-access.guard";
import { SsoProvider, StubSsoProvider } from "./sso.provider";
import { AuditModule } from "../audit/audit.module";

@Module({
  imports: [
    JwtModule.register({
      global: true,
      secret: process.env.JWT_ACCESS_SECRET ?? "dev-access-secret-change-me",
    }),
    AuditModule,
  ],
  controllers: [AuthController],
  providers: [
    AuthService,
    JwtAuthGuard,
    PermissionsGuard,
    TenantAccessGuard,
    { provide: SsoProvider, useClass: StubSsoProvider },
  ],
  exports: [AuthService, JwtAuthGuard, PermissionsGuard, TenantAccessGuard],
})
export class AuthModule {}
