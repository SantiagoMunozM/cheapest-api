import { Module } from '@nestjs/common';

// Database
import { DatabaseModule } from '../datasources/database.module';

// Repositories
import { repositoryProviders, TiendaRepository } from './repositories';

// Controllers
import { TiendaController } from './controllers';
import { TiendaService } from './services';

@Module({
  imports: [DatabaseModule],
  controllers: [TiendaController],
  providers: [
    // Repository Providers
    ...repositoryProviders,
    // Repositories
    TiendaRepository,
    // Services
    TiendaService,
  ],
  exports: [TiendaService],
})
export class IdentificacionModule {}
