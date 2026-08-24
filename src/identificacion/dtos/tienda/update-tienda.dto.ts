import {
  IsEnum,
  IsOptional,
  IsString,
  IsUUID,
  MaxLength,
} from 'class-validator';
import { EstadoCaptacion } from '../../repositories/entities/tienda.entity';

export class UpdateTiendaDto {
  @IsOptional()
  @IsString()
  @MaxLength(255)
  codigoInterno?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  nombreComercial?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  rut?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  direccion?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  telefono?: string;

  @IsOptional()
  @IsUUID()
  responsableId?: string;

  @IsOptional()
  @IsUUID()
  paisId?: string;

  @IsOptional()
  @IsEnum(EstadoCaptacion)
  estadoCaptacion?: EstadoCaptacion;
}
