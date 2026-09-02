package com.clearflow.gateway.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.RedisSerializer;

import com.clearflow.gateway.domain.PaymentResponse;

@Configuration
public class RedisConfig {

    @Bean
    @org.springframework.context.annotation.Primary
    public ReactiveRedisTemplate<String, String> reactiveRedisTemplate(ReactiveRedisConnectionFactory factory) {
        RedisSerializationContext<String, String> context = RedisSerializationContext
                .<String, String>newSerializationContext(RedisSerializer.string())
                .value(RedisSerializer.string())
                .build();
        return new ReactiveRedisTemplate<>(factory, context);
    }

    @Bean(name = "paymentResponseRedisTemplate")
    public ReactiveRedisTemplate<String, PaymentResponse> paymentResponseRedisTemplate(ReactiveRedisConnectionFactory factory) {
        ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule());
        Jackson2JsonRedisSerializer<PaymentResponse> serializer = new Jackson2JsonRedisSerializer<>(mapper, PaymentResponse.class);
        RedisSerializationContext<String, PaymentResponse> context = RedisSerializationContext
                .<String, PaymentResponse>newSerializationContext(RedisSerializer.string())
            .value(serializer)
                .build();
        return new ReactiveRedisTemplate<>(factory, context);
    }
}
