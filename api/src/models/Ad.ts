import mongoose, { Schema, Document } from 'mongoose'

export interface IAd extends Document {
  adId:         string
  advertiserId: string
  campaignId:   string
  title:        string
  description:  string
  imageUrl:     string
  destinationUrl: string
  adType:       'banner' | 'video' | 'native' | 'search'
  market:       string
  isActive:     boolean
  createdAt:    Date
  updatedAt:    Date
}

const AdSchema = new Schema<IAd>({
  adId:           { type: String, required: true, unique: true, index: true },
  advertiserId:   { type: String, required: true, index: true },
  campaignId:     { type: String, required: true, index: true },
  title:          { type: String, required: true },
  description:    { type: String },
  imageUrl:       { type: String },
  destinationUrl: { type: String, required: true },
  adType:         { type: String, enum: ['banner', 'video', 'native', 'search'], required: true },
  market:         { type: String, default: 'PT' },
  isActive:       { type: Boolean, default: true }
}, { timestamps: true })

export const Ad = mongoose.model<IAd>('Ad', AdSchema)
