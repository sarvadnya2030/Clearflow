package com.clearflow.validation.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.List;

@Component
public class EmbargoDataLoader {

    private static final Logger log = LoggerFactory.getLogger(EmbargoDataLoader.class);
    private final StringRedisTemplate redisTemplate;
    private final List<String> embargoedCountries;

    public EmbargoDataLoader(StringRedisTemplate redisTemplate,
                             @Value("${clearflow.embargo.countries:IR,KP,SY,CU,SD,MM,RU}") String countries) {
        this.redisTemplate = redisTemplate;
        this.embargoedCountries = Arrays.asList(countries.split(","));
    }

    // Runs after the full Spring context is up — avoids Lettuce/Netty deadlock
    // that occurs when a @PostConstruct tries to open a Redis connection while
    // the Lettuce event loop is still initialising (SharedConnection.doInLock
    // waits forever for a connection future that can't complete).
    @EventListener(ApplicationReadyEvent.class)
    public void load() {
        try {
            redisTemplate.opsForSet().add("embargoed:countries", embargoedCountries.toArray(String[]::new));
            log.info("Embargo country list loaded into Redis ({} countries)", embargoedCountries.size());
        } catch (Exception ex) {
            log.warn("EmbargoDataLoader: failed to seed Redis — embargo checks will miss data: {}", ex.getMessage());
        }
    }
}
