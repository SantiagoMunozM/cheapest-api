import { Injectable, NotFoundException } from '@nestjs/common';

import { TiendaRepository } from '../repositories';
import { Tienda } from '../repositories/entities';
import { CreateTiendaDto } from '../dtos/tienda/create-tienda.dto';
import { QueryTiendaDto } from '../dtos/tienda/query-tienda.dto';
import { TiendaResponseDto } from '../dtos/tienda/tienda-response.dto';
import { UpdateTiendaDto } from '../dtos/tienda/update-tienda.dto';

@Injectable()
export class TiendaService {
  constructor(private readonly tiendaRepository: TiendaRepository) {}

  async create(dto: CreateTiendaDto): Promise<TiendaResponseDto> {
    const tienda = await this.tiendaRepository.create(dto);
    return this.mapToResponse(tienda);
  }

  async findAll(query: QueryTiendaDto): Promise<TiendaResponseDto[]> {
    const tiendas = await this.tiendaRepository.findAll(query);

    return tiendas.map((tienda) => this.mapToResponse(tienda));
  }

  async findById(id: string): Promise<TiendaResponseDto> {
    const tienda = await this.tiendaRepository.findById(id);
    if (!tienda) {
      throw new NotFoundException(`Tienda con id ${id} no encontrada`);
    }

    return this.mapToResponse(tienda);
  }

  async update(id: string, dto: UpdateTiendaDto): Promise<TiendaResponseDto> {
    const tienda = await this.tiendaRepository.findById(id);
    if (!tienda) {
      throw new NotFoundException(`Tienda con id ${id} no encontrada`);
    }

    const updatedTienda = await this.tiendaRepository.update(id, dto);
    return this.mapToResponse(updatedTienda!);
  }

  async delete(id: string): Promise<void> {
    const tienda = await this.tiendaRepository.findById(id);
    if (!tienda) {
      throw new NotFoundException(`Tienda con id ${id} no encontrada`);
    }

    await this.tiendaRepository.delete(id);
  }

  private mapToResponse(tienda: Tienda): TiendaResponseDto {
    return {
      id: tienda.id,
      codigoInterno: tienda.codigoInterno,
      nombreComercial: tienda.nombreComercial,
      rut: tienda.rut,
      direccion: tienda.direccion,
      telefono: tienda.telefono,
      responsableId: tienda.responsableId,
      paisId: tienda.paisId,
      estadoCaptacion: tienda.estadoCaptacion,
    };
  }
}
