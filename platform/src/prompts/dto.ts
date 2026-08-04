import { IsBoolean, IsOptional, IsString } from "class-validator";

export class CreatePromptTemplateDto {
  @IsString()
  title!: string;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  @IsString()
  category?: string;

  @IsOptional()
  @IsString()
  conversationFlow?: string;

  @IsOptional()
  @IsString()
  openingInstructions?: string;

  @IsOptional()
  @IsString()
  silenceInstructions?: string;

  @IsOptional()
  @IsString()
  systemBoundaries?: string;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;
}

export class UpdatePromptTemplateDto {
  @IsOptional()
  @IsString()
  title?: string;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  @IsString()
  category?: string;

  @IsOptional()
  @IsString()
  conversationFlow?: string;

  @IsOptional()
  @IsString()
  openingInstructions?: string;

  @IsOptional()
  @IsString()
  silenceInstructions?: string;

  @IsOptional()
  @IsString()
  systemBoundaries?: string;

  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;
}
