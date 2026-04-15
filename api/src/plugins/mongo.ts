import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import mongoose from 'mongoose'

const mongoPlugin: FastifyPluginAsync = fp(async (app) => {
  const url = process.env.MONGO_URL || 'mongodb://lab:labpass@mongodb:27017/adlab?authSource=admin'
  
  try {
    await mongoose.connect(url, { serverSelectionTimeoutMS: 3000 })
    app.log.info('MongoDB connected')
  } catch (err) {
    // Non-fatal in K8s — MongoDB may not be deployed
    app.log.warn('MongoDB unavailable — continuing without it')
  }
})

export { mongoPlugin }
