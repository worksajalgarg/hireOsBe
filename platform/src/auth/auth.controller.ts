import { Body, Controller, HttpCode, Post, Req, Res } from "@nestjs/common";import { ApiTags } from "@nestjs/swagger";
import type { Request, Response } from "express";
import { AuthService } from "./auth.service";
import { Public } from "./public.decorator";
import {
  AcceptInviteDto,
  ForgotPasswordDto,
  LoginDto,
  MfaVerifyDto,
  ResetPasswordDto,
  SsoCallbackDto,
} from "./dto";
import { REFRESH_COOKIE_NAME } from "./auth.types";
import { CurrentUser } from "./auth.decorators";

@ApiTags("auth")
@Controller("auth")
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  private setRefreshCookie(res: Response, refreshToken: string) {
    res.cookie(REFRESH_COOKIE_NAME, refreshToken, {
      httpOnly: true,
      secure: process.env.COOKIE_SECURE === "true",
      sameSite: "lax",
      path: "/api/v1/auth",
      maxAge: 30 * 24 * 60 * 60 * 1000,
    });
  }

  private clearRefreshCookie(res: Response) {
    res.clearCookie(REFRESH_COOKIE_NAME, {
      path: "/api/v1/auth",
      httpOnly: true,
      secure: process.env.COOKIE_SECURE === "true",
      sameSite: "lax",
    });
  }

  @Public()
  @Post("login")
  @HttpCode(200)
  async login(@Body() dto: LoginDto, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    const result = await this.authService.login(dto, {
      userAgent: req.headers["user-agent"],
      ipAddress: req.ip,
    });
    const { refreshToken, ...body } = result;
    this.setRefreshCookie(res, refreshToken);
    return body;
  }

  @Public()
  @Post("refresh")
  @HttpCode(200)
  async refresh(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    const token = (req as Request & { cookies?: Record<string, string> }).cookies?.[REFRESH_COOKIE_NAME];
    const result = await this.authService.refresh(token, {
      userAgent: req.headers["user-agent"],
      ipAddress: req.ip,
    });
    const { refreshToken, ...body } = result;
    this.setRefreshCookie(res, refreshToken);
    return body;
  }

  @Post("logout")
  @HttpCode(200)
  async logout(
    @CurrentUser() user: { id?: string; tenantId?: string; sessionId?: string },
    @Res({ passthrough: true }) res: Response,
  ) {
    await this.authService.logout(user.sessionId, user.id, user.tenantId);
    this.clearRefreshCookie(res);
    return { ok: true };
  }

  @Public()
  @Post("sso/callback")
  @HttpCode(200)
  async ssoCallback(
    @Body() dto: SsoCallbackDto,
    @Req() req: Request,
    @Res({ passthrough: true }) res: Response,
  ) {
    const result = await this.authService.ssoCallback(dto, {
      userAgent: req.headers["user-agent"],
      ipAddress: req.ip,
    });
    const { refreshToken, ...body } = result;
    this.setRefreshCookie(res, refreshToken);
    return body;
  }

  @Public()
  @Post("forgot-password")
  @HttpCode(200)
  async forgotPassword(@Body() dto: ForgotPasswordDto) {
    return this.authService.forgotPassword(dto);
  }

  @Public()
  @Post("reset-password")
  @HttpCode(200)
  async resetPassword(@Body() dto: ResetPasswordDto) {
    return this.authService.resetPassword(dto);
  }

  @Public()
  @Post("mfa/verify")
  @HttpCode(200)
  async mfaVerify(@Body() _dto: MfaVerifyDto) {
    return this.authService.mfaVerify();
  }

  @Public()
  @Post("accept-invite")
  @HttpCode(200)
  async acceptInvite(@Body() dto: AcceptInviteDto) {
    return this.authService.acceptInvite(dto);
  }
}
