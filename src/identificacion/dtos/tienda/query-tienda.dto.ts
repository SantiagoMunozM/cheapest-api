import { IsEnum, IsOptional, IsUUID } from 'class-validator';
import { EstadoCaptacion } from '../../repositories/entities/tienda.entity';

export class QueryTiendaDto {
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
