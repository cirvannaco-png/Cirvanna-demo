import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('pending_evolutions')
export class PendingEvolutionEntity {
  @PrimaryColumn() userId: string;
  @Column() eventId: string;
  @Column('jsonb') event: any; // EvolutionEvent
  @Column() timeoutAt: Date;
}
