import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { ValidationPipe } from "@nestjs/common";
import cookieParser from "cookie-parser";
import { AppModule } from "../src/app.module";

let appInstance: any = null;

export default async function handler(req: any, res: any) {
  if (req.url === "/" || req.url === "/health" || req.url === "/api/index") {
    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({ status: "ok", service: "hireOs Platform API", version: "1.0.0" }));
  }
  if (!appInstance) {
    const app = await NestFactory.create(AppModule);
    app.setGlobalPrefix("api/v1");
    app.use(cookieParser());
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    app.enableCors({
      origin: true,
      credentials: true,
    });
    await app.init();
    appInstance = app.getHttpAdapter().getInstance();
  }
  return appInstance(req, res);
}
