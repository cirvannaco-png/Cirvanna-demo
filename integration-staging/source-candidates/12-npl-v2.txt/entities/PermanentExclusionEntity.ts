import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('permanent_exclusions')
export class PermanentExclusionEntity {
  @PrimaryColumn() userId: string;
  @PrimaryColumn() itemId: string;
  @Column() domain: string;
  @Column() rejectionCount: number;
  @Column() threshold: number;
  @Column() reason: string;
  @Column('float') rigidityAtTime: number;
  @Column() createdAt: Date;
}
