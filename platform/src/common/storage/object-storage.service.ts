import { Injectable, Logger, OnModuleInit } from "@nestjs/common";
import {
  CreateBucketCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { Readable } from "stream";

@Injectable()
export class ObjectStorageService implements OnModuleInit {
  private readonly logger = new Logger(ObjectStorageService.name);
  private readonly client: S3Client;
  private readonly bucket: string;

  constructor() {
    const endpoint = process.env.S3_ENDPOINT ?? "http://localhost:9000";
    const region = process.env.S3_REGION ?? "us-east-1";
    const accessKeyId = process.env.S3_ACCESS_KEY ?? "platform";
    const secretAccessKey = process.env.S3_SECRET_KEY ?? "platform123";
    this.bucket = process.env.S3_BUCKET ?? "hireos-resumes";

    this.client = new S3Client({
      region,
      endpoint,
      forcePathStyle: process.env.S3_FORCE_PATH_STYLE !== "false",
      credentials: { accessKeyId, secretAccessKey },
    });
  }

  async onModuleInit() {
    await this.ensureBucket();
  }

  private async ensureBucket() {
    try {
      await this.client.send(new HeadBucketCommand({ Bucket: this.bucket }));
    } catch {
      try {
        await this.client.send(new CreateBucketCommand({ Bucket: this.bucket }));
        this.logger.log(`Created MinIO bucket ${this.bucket}`);
      } catch (err) {
        this.logger.warn(
          `Could not ensure bucket ${this.bucket} (is MinIO running?): ${(err as Error).message}`,
        );
      }
    }
  }

  buildResumeKey(tenantId: string, resumeId: string, filename: string): string {
    const safe = filename.replace(/[/\\]/g, "_").replace(/\0/g, "");
    return `${tenantId}/resumes/${resumeId}/${safe}`;
  }

  async putObject(params: {
    key: string;
    body: Buffer;
    contentType: string;
  }): Promise<void> {
    try {
      await this.client.send(
        new PutObjectCommand({
          Bucket: this.bucket,
          Key: params.key,
          Body: params.body,
          ContentType: params.contentType,
        }),
      );
    } catch (err) {
      this.logger.warn(
        `ObjectStorageService: S3/MinIO endpoint unreachable for key ${params.key}: ${(err as Error).message}`,
      );
    }
  }

  async getObjectBuffer(key: string): Promise<Buffer> {
    try {
      const result = await this.client.send(
        new GetObjectCommand({ Bucket: this.bucket, Key: key }),
      );
      const body = result.Body;
      if (!body) {
        throw new Error(`Empty object body for key ${key}`);
      }
      return await this.streamToBuffer(body as Readable);
    } catch (err) {
      this.logger.warn(
        `ObjectStorageService: getObjectBuffer failed for key ${key}: ${(err as Error).message}`,
      );
      return Buffer.from("");
    }
  }

  async deleteObject(key: string): Promise<void> {
    await this.client.send(
      new DeleteObjectCommand({ Bucket: this.bucket, Key: key }),
    );
  }

  private async streamToBuffer(stream: Readable): Promise<Buffer> {
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }
    return Buffer.concat(chunks);
  }
}
