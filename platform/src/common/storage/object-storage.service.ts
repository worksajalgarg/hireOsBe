import { Injectable } from "@nestjs/common";
import {
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

/** General-purpose S3/MinIO client for arbitrary file uploads (resumes, JD
 * files) — distinct from interviews/livekit.service.ts's `S3Upload`, which
 * is a LiveKit Egress proto type only LiveKit's own Egress service uses, not
 * a client platform can call directly for uploads outside that flow.
 *
 * Upload is server-mediated (browser -> platform -> S3), not presigned
 * direct-PUT — platform validates MIME/magic-bytes and computes the sha256
 * dedupe hash before anything lands in the bucket, so we don't hand out
 * unauthenticated write access. Presigned URLs are used for download only. */
@Injectable()
export class ObjectStorageService {
  private readonly client = new S3Client({
    endpoint: requireEnv("MINIO_ENDPOINT", "http://minio:9000"),
    region: process.env.S3_REGION || "us-east-1",
    forcePathStyle: (process.env.S3_FORCE_PATH_STYLE ?? "true") === "true",
    credentials: {
      accessKeyId: requireEnv("MINIO_ACCESS_KEY", "platform"),
      secretAccessKey: requireEnv("MINIO_SECRET_KEY", "platform123"),
    },
  });

  async put(params: {
    bucket: string;
    key: string;
    body: Buffer;
    contentType: string;
  }): Promise<void> {
    await this.client.send(
      new PutObjectCommand({
        Bucket: params.bucket,
        Key: params.key,
        Body: params.body,
        ContentType: params.contentType,
      }),
    );
  }

  async get(params: { bucket: string; key: string }): Promise<Buffer> {
    const res = await this.client.send(new GetObjectCommand({ Bucket: params.bucket, Key: params.key }));
    const bytes = await res.Body?.transformToByteArray();
    if (!bytes) throw new Error(`Object ${params.bucket}/${params.key} has no body`);
    return Buffer.from(bytes);
  }

  async getSignedDownloadUrl(params: {
    bucket: string;
    key: string;
    expiresInSeconds?: number;
  }): Promise<string> {
    return getSignedUrl(
      this.client,
      new GetObjectCommand({ Bucket: params.bucket, Key: params.key }),
      { expiresIn: params.expiresInSeconds ?? 300 },
    );
  }

  async delete(params: { bucket: string; key: string }): Promise<void> {
    await this.client.send(
      new DeleteObjectCommand({ Bucket: params.bucket, Key: params.key }),
    );
  }
}

function requireEnv(name: string, devDefault?: string): string {
  const value = process.env[name] ?? devDefault;
  if (!value) {
    throw new Error(`Missing required env var ${name}`);
  }
  return value;
}
