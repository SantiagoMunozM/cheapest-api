import { EstadoCaptacion } from '../../repositories/entities/tienda.entity';

export class TiendaResponseDto {
  id: string;
  codigoInterno: string;
  nombreComercial: string;
  rut: string;
  direccion: string;
  telefono: string;
  responsableId?: string;
  paisId?: string;
  estadoCaptacion: EstadoCaptacion;
}
