import {
  IsEnum,
  IsOptional,
  IsString,
  IsUUID,
  MaxLength,
} from 'class-validator';
import { EstadoCaptacion } from '../../repositories/entities/tienda.entity';

export class CreateTiendaDto {
  @IsString()
  @MaxLength(255)
  codigoInterno: string;

  @IsString()
  @MaxLength(255)
  nombreComercial: string;

  @IsString()
  @MaxLength(255)
  rut: string;

  @IsString()
  @MaxLength(255)
  direccion: string;

  @IsString()
  @MaxLength(255)
  telefono: string;

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
