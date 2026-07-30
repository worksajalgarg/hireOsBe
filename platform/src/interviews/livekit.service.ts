import { Injectable, Logger } from "@nestjs/common";
import { AccessToken, EgressClient, RoomServiceClient, VideoGrant } from "livekit-server-sdk";
import { EncodedFileOutput, EncodedFileType, S3Upload } from "@livekit/protocol";

/** RoomServiceClient/EgressClient talk Twirp-over-HTTP; only the media/signaling
 * path (used by browser/agent clients, not this service) is ws://. */
function toHttpUrl(wsUrl: string): string {
  return wsUrl.replace(/^ws/, "http");
}

@Injectable()
export class LiveKitService {
  private readonly logger = new Logger(LiveKitService.name);

  private readonly apiKey = requireEnv("LIVEKIT_API_KEY");
  private readonly apiSecret = requireEnv("LIVEKIT_API_SECRET");
  private readonly wsUrl = requireEnv("LIVEKIT_URL");

  private readonly roomService = new RoomServiceClient(
    toHttpUrl(this.wsUrl),
    this.apiKey,
    this.apiSecret,
  );
  private readonly egressClient = new EgressClient(
    toHttpUrl(this.wsUrl),
    this.apiKey,
    this.apiSecret,
  );

  get url(): string {
    return this.wsUrl;
  }

  /** Creates the room up front (rather than relying on join-triggered auto-creation)
   * so room metadata — read by the voice agent worker on dispatch — is present
   * before anyone can join. `emptyTimeout` is set to match the invite link's
   * validity window, not LiveKit's 300s default — otherwise the room gets
   * reaped by the server before a candidate who takes a few minutes to open
   * the link ever gets to join it ("requested room does not exist"). */
  async createRoom(roomName: string, metadata: Record<string, unknown>, emptyTimeoutSeconds: number) {
    return this.roomService.createRoom({
      name: roomName,
      metadata: JSON.stringify(metadata),
      emptyTimeout: emptyTimeoutSeconds,
    });
  }

  async mintToken(params: {
    identity: string;
    roomName: string;
    grant: VideoGrant;
    ttlSeconds?: number;
  }): Promise<string> {
    const token = new AccessToken(this.apiKey, this.apiSecret, {
      identity: params.identity,
      ttl: params.ttlSeconds ?? 30 * 60,
    });
    token.addGrant({ room: params.roomName, ...params.grant });
    return token.toJwt();
  }

  /** Voice-only interview — records audio composite, no video track, to the
   * tenant-prefixed S3(MinIO) object key the caller provides. */
  async startRoomCompositeEgress(roomName: string, s3ObjectKey: string): Promise<{ egressId: string }> {
    const output = new EncodedFileOutput({
      fileType: EncodedFileType.MP4,
      filepath: s3ObjectKey,
      output: {
        case: "s3",
        value: new S3Upload({
          accessKey: requireEnv("MINIO_ACCESS_KEY", "platform"),
          secret: requireEnv("MINIO_SECRET_KEY", "platform123"),
          bucket: requireEnv("RECORDINGS_BUCKET", "interview-recordings"),
          endpoint: requireEnv("MINIO_ENDPOINT", "http://minio:9000"),
          forcePathStyle: true,
          region: "us-east-1",
        }),
      },
    });

    const info = await this.egressClient.startRoomCompositeEgress(roomName, output, {
      audioOnly: true,
    });
    this.logger.log(`Started egress ${info.egressId} for room ${roomName}`);
    return { egressId: info.egressId };
  }

  async stopEgress(egressId: string): Promise<void> {
    await this.egressClient.stopEgress(egressId);
  }
}

function requireEnv(name: string, devDefault?: string): string {
  const value = process.env[name] ?? devDefault;
  if (!value) {
    throw new Error(`Missing required env var ${name}`);
  }
  return value;
}
